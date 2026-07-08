import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Callable


def _debug_log(msg: str) -> None:
    """Log discreto em stderr — aparece no terminal (main.py) mas nao no
    painel UI. Silencioso no .exe compilado sem console (windowed mode)."""
    try:
        sys.stderr.write(f"[dbg] {msg}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass  # stderr fechado ou stdout redirecionado

from config import GOIANIA_DDD, GOIANIA_IBGE_7, GOIANIA_IBGE_6
from core.xml_parser import eh_evento_cancelamento, detectar_padrao_nfse
from core.extractor import extrair_dados_python, extrair_cabecalho_info
from core.validators import normalize_digits, eh_goiania, eh_municipio_aceito, item_lc_valido
from core.txt_builder import montar_linha_txt, montar_cabecalho
from services.ibge import consulta_cidade_ibge
from services.cep import consultar_cep, ddd_por_uf, obter_cep_generico_municipio
from services.cnpj import consultar_cnpj
from services.n8n_client import chamar_n8n
from services.spreadsheet import get_company_info
from services.autmais_api import (
    baixar_xmls_da_empresa,
    vigencia_mmaaaa_para_yyyymm,
    get_cliente as get_cliente_autmais,
    AutmaisAPIError,
)


class ProcessorResult:
    __slots__ = (
        "linhas_dict", "relatorio", "notas_vig_errada",
        "im_tomador_cab", "razao_tomador_cab", "conteudo_final",
        "cnpj_tomador_cab",
    )

    def __init__(self, linhas_dict, relatorio, notas_vig_errada,
                 im_tomador_cab, razao_tomador_cab, conteudo_final,
                 cnpj_tomador_cab=""):
        self.linhas_dict = linhas_dict
        self.relatorio = relatorio
        self.notas_vig_errada = notas_vig_errada
        self.im_tomador_cab = im_tomador_cab
        self.razao_tomador_cab = razao_tomador_cab
        self.conteudo_final = conteudo_final
        self.cnpj_tomador_cab = cnpj_tomador_cab


def _parse_json_safe(response):
    """Tenta parsear JSON da resposta N8N. Retorna None se falhar."""
    try:
        return response.json()
    except (ValueError, AttributeError):
        return None


def _extrair_n8n_obj(js, raw_text: str = ""):
    """Extrai o objeto principal da resposta N8N (list[0], dict ou regex fallback)."""
    if isinstance(js, list) and js and isinstance(js[0], dict):
        return js[0]
    if isinstance(js, dict):
        return js
    if raw_text:
        ext = {}
        # Inclui itemLC/DDD/itemLc para resiliência se o JSON falhar.
        campos = (
            "ddd", "DDD", "itemLC", "itemLc", "item_lc",
            "status", "motivo", "item_lc_original",
            "chave_nfse", "localidade", "method",
            "item_lc_final", "confidence_score", "confidence_level",
        )
        for campo in campos:
            m = re.search(rf'"{campo}"\s*:\s*"?(.*?)"?\s*[,}}]', raw_text, re.DOTALL)
            if m:
                val = m.group(1).strip().strip('"')
                if val:
                    ext[campo] = val
        return ext or None
    return None


def _extrair_ddd_itemlc(n8n_obj: dict | None) -> tuple[str, str]:
    """Extrai DDD e Item LC de um objeto N8N.

    Tolera variações de capitalização (DDD/ddd, itemLC/itemLc/item_lc/item_lc_final)
    para resistir a mudanças no template do workflow.
    """
    if not n8n_obj:
        return "", ""
    ddd = item_lc = ""
    lf = str(n8n_obj.get("linha_final", "")).strip()
    if lf:
        parts = [p.strip() for p in lf.split(";")]
        if len(parts) >= 2:
            ddd, item_lc = parts[0], parts[1]
    if not ddd:
        for chave in ("DDD", "ddd"):
            v = str(n8n_obj.get(chave, "") or "").strip()
            if v:
                ddd = v
                break
    if not item_lc:
        for chave in ("itemLC", "itemLc", "item_lc", "item_lc_final"):
            v = str(n8n_obj.get(chave, "") or "").strip()
            if v:
                item_lc = v
                break
    return ddd, item_lc


_FORMAS_NAO_MEI = (" LTDA", " S/A", " S.A.", " S A ", " S.A ", " SA ",
                    "EIRELI", " S/S", "EPP", " ME EPP")


def _eh_pessoa_juridica_por_razao(razao: str) -> bool:
    """Veto: LTDA/S.A./EIRELI/etc não podem ser MEI."""
    r = f" {(razao or '').upper()} "
    return any(f in r for f in _FORMAS_NAO_MEI)


def _enriquecer_optante_via_cnpj(dados: dict) -> None:
    """Consulta BrasilAPI/CNPJ.ws para descobrir SN/MEI do prestador.

    Só roda para prestadores fora de Goiânia (onde a tag costuma faltar) e
    só quando o XML não trouxe a informação (`optante_sn_mei` vazio).
    Mantém o veto de pessoa jurídica para evitar marcar LTDA como MEI.
    """
    if eh_goiania(dados):
        return
    if (dados.get("optante_sn_mei") or "").strip():
        return  # XML já trouxe info — preserva
    info = consultar_cnpj(dados.get("cnpj_p", ""))
    if not info:
        return
    if info.get("mei") and not _eh_pessoa_juridica_por_razao(dados.get("razao_p", "")):
        dados["optante_sn_mei"] = "3"
    elif info.get("simples_nacional") or info.get("mei"):
        dados["optante_sn_mei"] = "2"
    else:
        dados["optante_sn_mei"] = "1"


def _enriquecer_dados_via_cep(dados: dict) -> str:
    """Consulta ViaCEP e preenche campos vazios em `dados`. Retorna DDD ou ''.

    Substitui a antiga consulta de CEP que era feita no n8n. Só preenche campos
    que estão vazios — preserva dados extraídos do XML quando presentes.
    """
    info = consultar_cep(dados.get("cep", ""))
    ddd = ""
    if info:
        if not (dados.get("endereco") or "").strip():
            dados["endereco"] = info.get("logradouro", "")
        if not (dados.get("bairro") or "").strip():
            dados["bairro"] = info.get("bairro", "")
        if not (dados.get("uf") or "").strip():
            dados["uf"] = info.get("uf", "")
        if not (dados.get("cidade_override") or "").strip():
            dados["cidade_override"] = info.get("cidade", "")
        ddd = info.get("ddd", "") or ""

    # Substituição de CEP genérico quando a nota traz CEP zerado/inválido.
    # ISSNet rejeita 00000000 — então buscamos um CEP qualquer da mesma cidade
    # (via ViaCEP search) e usamos no lugar. O endereço do prestador continua
    # vindo do XML; só o CEP é "remendado" para ser aceito no portal.
    _cep_atual = normalize_digits(dados.get("cep", ""))
    if _cep_atual == "00000000" or len(_cep_atual) != 8:
        cidade_busca = (dados.get("cidade_override") or "").strip()
        if not cidade_busca:
            for ibge_field in ("codigo_municipio", "local_prestacao"):
                cidade_busca = consulta_cidade_ibge(dados.get(ibge_field, ""))
                if cidade_busca:
                    break
        cep_substituto = obter_cep_generico_municipio(
            dados.get("uf", ""), cidade_busca
        )
        if cep_substituto:
            dados["cep"] = cep_substituto
            # Tenta enriquecer DDD pelo novo CEP, se ainda não temos
            if not ddd:
                info2 = consultar_cep(cep_substituto)
                if info2:
                    ddd = info2.get("ddd", "") or ddd

    # Fallback final: se as APIs não devolveram DDD, usa o DDD principal do UF.
    if not ddd:
        ddd = ddd_por_uf(dados.get("uf", ""))

    return ddd


def _bundle_descricoes(dados: dict) -> dict:
    """Bundle de todas as descrições mostradas na tela de fallback manual,
    enviado ao n8n para o agente de IA classificar o Item LC.

    Espelha o conteúdo visível em ui/dialogs.py:abrir_tela_manual_itemlc:
    - descricao_principal: campo grande no topo (Discriminacao/xDescServ/xTribNac)
    - cTribNac, xTribNac, xTribMun, xNBS: tags adicionais do XML
    - discriminacao, x_desc_serv: campos raw para cobertura completa
    """
    return {
        "descricao_principal": dados.get("descricao_servico", ""),
        "discriminacao":       dados.get("discriminacao", ""),
        "x_desc_serv":         dados.get("x_desc_serv", ""),
        "c_trib_nac":          dados.get("c_trib_nac", ""),
        "x_trib_nac":          dados.get("x_trib_nac", ""),
        "x_trib_mun":          dados.get("x_trib_mun", ""),
        "x_nbs":               dados.get("x_nbs", ""),
    }


def _relatorio_row(nome, dados, status, modo, detalhe):
    """Monta uma linha de relatório no formato padrão."""
    return [
        nome,
        dados.get("cnpj_p", ""),
        dados.get("numero", ""),
        dados.get("vlr_doc", ""),
        status, modo, detalhe,
    ]


class WorkflowProcessor:

    def __init__(self, log_fn: Callable, progress_fn: Callable, contador_fn: Callable,
                 abrir_tela_manual_fn: Callable, gerar_mei: bool = False,
                 marcar_baixadas: bool = False):
        self._log = log_fn
        self._set_progress = progress_fn
        self._set_contador = contador_fn
        self._abrir_tela_manual = abrir_tela_manual_fn
        self._gerar_mei = gerar_mei
        self._marcar_baixadas = marcar_baixadas
        self._chaves_baixadas: list[str] = []

    def processar(self, emp_cod: str, vigencia: str,
                  empresa_ibge: str = "") -> ProcessorResult | None:
        # Guarda IBGE da empresa tomadora pra uso em montar_linha_txt.
        # Compara com codigo_municipio do PRESTADOR pra decidir modelo (2=mesmo mun, 4=fora).
        self._empresa_ibge = empresa_ibge
        self._chaves_baixadas = []
        try:
            dict_xmls = self._baixar_xmls_via_api(emp_cod, vigencia)
        except AutmaisAPIError as e:
            self._log(f"❌ Erro na API Autmais: {e}")
            return None

        if not dict_xmls:
            self._log("❌ Nenhuma nota encontrada na API para essa empresa/vigência.")
            return None

        if not self._validar_tomador_goiania(dict_xmls):
            return None

        notas_xmls, chaves_canceladas = self._separar_eventos(dict_xmls)
        linhas_dict, relatorio, _chave_map, _ts_map = self._processar_notas(
            notas_xmls, chaves_canceladas, dict_xmls, vigencia
        )

        notas_vig_errada = self._filtrar_vigencia(linhas_dict, vigencia, emp_cod)

        conteudo_final = ""
        im_tomador_cab, razao_tomador_cab, cabecalho, cnpj_tomador_cab = self._gerar_cabecalho(dict_xmls, emp_cod, vigencia)

        if linhas_dict:
            linhas_txt = ([cabecalho] if cabecalho else []) + list(linhas_dict.values())
            conteudo_final = "\n".join(linhas_txt)
            self._enriquecer_relatorio(relatorio, linhas_txt, _chave_map, _ts_map)
            self._log(f"🏁 Concluído! {len(linhas_dict)} nota(s) processada(s) com sucesso.")
        else:
            self._enriquecer_relatorio_vazio(relatorio, _chave_map, _ts_map)
            if notas_vig_errada:
                total_div = sum(len(v) for v in notas_vig_errada.values())
                self._log(f"⚠️ {total_div} nota(s) processada(s), mas de outra vigência.")
            else:
                self._log("❌ Nenhuma nota foi processada com sucesso.")

        return ProcessorResult(
            linhas_dict=linhas_dict,
            relatorio=relatorio,
            notas_vig_errada=notas_vig_errada,
            im_tomador_cab=im_tomador_cab,
            razao_tomador_cab=razao_tomador_cab,
            conteudo_final=conteudo_final,
            cnpj_tomador_cab=cnpj_tomador_cab,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Carregamento e separação de XMLs
    # ──────────────────────────────────────────────────────────────────────────

    def _carregar_xmls(self, pasta: Path) -> dict:
        """[LEGADO] leitura de disco. Mantido como fallback se necessario."""
        dict_xmls = {}
        for arq in pasta.glob("*"):
            if arq.suffix.lower() == ".xml":
                dict_xmls[arq.name] = arq.read_text(encoding="utf-8", errors="ignore")
            elif arq.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(arq, 'r') as z:
                        for n in z.namelist():
                            if n.lower().endswith(".xml"):
                                dict_xmls[n] = z.read(n).decode("utf-8", errors="ignore")
                except (zipfile.BadZipFile, OSError):
                    pass
        return dict_xmls

    def _baixar_xmls_via_api(self, emp_cod: str, vigencia: str) -> dict:
        """Wrapper sobre autmais_api.baixar_xmls_da_empresa.

        Vigencia legada chega como mmaaaa ('052026'); converte pra YYYY-MM.
        Se marcar_baixadas estiver ligado, coleta chaves em self._chaves_baixadas
        para serem marcadas via PUT /status_download apos a geracao bem-sucedida.
        """
        yyyymm = vigencia_mmaaaa_para_yyyymm(vigencia)
        return baixar_xmls_da_empresa(
            emp_cod, yyyymm,
            log_fn=self._log,
            chaves_out=self._chaves_baixadas if self._marcar_baixadas else None,
        )

    def marcar_baixadas_na_autmais(self) -> int:
        """Chama PUT /notas_servico/status_download para as chaves baixadas na
        ultima execucao de processar(). Devolve a quantidade marcada.
        Best-effort: erros silenciosos (geracao ja foi sucesso)."""
        if not self._marcar_baixadas or not self._chaves_baixadas:
            return 0
        try:
            r = get_cliente_autmais().marcar_baixadas(self._chaves_baixadas)
            return int(r.get("modifiedCount", 0))
        except AutmaisAPIError:
            return 0

    def _separar_eventos(self, dict_xmls: dict):
        notas_xmls = {}
        chaves_canceladas = set()
        for nome, conteudo in dict_xmls.items():
            if "_event_" in nome.lower():
                if eh_evento_cancelamento(conteudo):
                    chave_nota = nome.split("_event_")[0]
                    chaves_canceladas.add(chave_nota)
                    self._log(f"⚠️ Nota cancelada detectada: {chave_nota}")
            else:
                notas_xmls[nome] = conteudo
        return notas_xmls, chaves_canceladas

    # ──────────────────────────────────────────────────────────────────────────
    # Processamento principal
    # ──────────────────────────────────────────────────────────────────────────

    def _processar_notas(self, notas_xmls, chaves_canceladas, dict_xmls, vigencia):
        relatorio = []
        linhas_dict = {}
        _chave_map = {}
        _ts_map = {}

        notas_filtradas = {}
        for nome, conteudo in notas_xmls.items():
            chave_sem_ext = nome.replace(".xml", "").replace(".XML", "")
            if chave_sem_ext in chaves_canceladas:
                self._log(f"⛔ Nota cancelada, será ignorada: {nome}")
                _ts_map[nome] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                relatorio.append([nome, "", "", "", "Ignorada", "-", "Nota cancelada"])
            else:
                notas_filtradas[nome] = conteudo

        def _prioridade(item):
            try:
                r = ET.fromstring(item[1])
                p = detectar_padrao_nfse(r)
                return 2 if p == "abrasf" else (1 if p == "nacional" else 0)
            except ET.ParseError:
                return 0

        notas_ordenadas = sorted(notas_filtradas.items(), key=_prioridade)
        total = len(notas_filtradas)
        self._set_progress(total)

        cancelamentos = len(chaves_canceladas)
        self._log(
            f"📂 {len(dict_xmls)} arquivo(s) encontrado(s)"
            + (f" — {cancelamentos} cancelamento(s) identificado(s)." if cancelamentos else ".")
        )
        self._log(f"📋 {total} nota(s) para processar.")
        self._log("─" * 48)

        for i, (nome, conteudo) in enumerate(notas_ordenadas, 1):
            self._set_contador(i, total)
            _ts_map[nome] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            status, dados = extrair_dados_python(conteudo)
            _chave_map[nome] = dados.get("chave_nfse", "")

            _chave_dedup = f"{dados.get('numero', '')}_{dados.get('cnpj_p', '')}"
            _padrao_atual = dados.get("padrao", "")
            if _chave_dedup and _chave_dedup != "_" and _chave_dedup in linhas_dict and _padrao_atual != "abrasf":
                self._log(f"⏭ Nota duplicada, ignorada: {nome}")
                relatorio.append(_relatorio_row(nome, dados, "Ignorada", "-", f"Duplicata ({_padrao_atual})"))
                continue

            if status == "desconhecido":
                self._processar_ia_extract(nome, conteudo, dados, linhas_dict, relatorio, i)
                continue

            if status != "completo":
                _debug_log(
                    f"[extract:{status}] {nome} | faltando={dados.get('_faltando') or '?'} | "
                    f"lc={dados.get('item_lc_final','')!r} "
                    f"cm={dados.get('codigo_municipio','')!r} "
                    f"lp={dados.get('local_prestacao','')!r}"
                )
                self._processar_ia_extract_incompleto(nome, conteudo, dados, linhas_dict, relatorio, i)
                continue

            if eh_goiania(dados):
                self._processar_goiania(nome, conteudo, dados, linhas_dict, relatorio)
                continue

            self._processar_map_only(nome, conteudo, dados, linhas_dict, relatorio, i)

        self._log("─" * 48)
        self._set_contador(0, 0)
        return linhas_dict, relatorio, _chave_map, _ts_map

    # ──────────────────────────────────────────────────────────────────────────
    # Processamento por modo
    # ──────────────────────────────────────────────────────────────────────────

    def _enriquecer_para_n8n(self, dados: dict) -> None:
        """Preenche campos que o n8n espera em dados_parciais antes de mandar.

        Sem isso, expression do n8n gera [undefined] pra ddd/cidade/uf.
        Faz ViaCEP + IBGE lookup + fallback DDD por UF.
        """
        # ViaCEP: preenche endereco, bairro, uf, cidade_override, ddd
        ddd = _enriquecer_dados_via_cep(dados)
        if ddd and not (dados.get("ddd") or "").strip():
            dados["ddd"] = ddd

        # Cidade: cascade (override -> IBGE codigo_municipio -> IBGE local_prestacao)
        if not (dados.get("cidade_override") or "").strip():
            cid = (
                consulta_cidade_ibge(dados.get("codigo_municipio", ""))
                or consulta_cidade_ibge(dados.get("local_prestacao", ""))
                or ""
            )
            if cid:
                dados["cidade_override"] = cid
                dados["cidade"] = cid   # espelha em `cidade` tb (n8n usa fallback)

        # DDD fallback por UF quando ViaCEP falhou
        if not (dados.get("ddd") or "").strip():
            _ddd_uf = ddd_por_uf(dados.get("uf", ""))
            if _ddd_uf:
                dados["ddd"] = _ddd_uf

        # Optante: garante default '1' pra n8n nao gerar undefined
        if not (dados.get("optante_sn_mei") or "").strip():
            dados["optante_sn_mei"] = "1"

    def _processar_ia_extract(self, nome, conteudo, dados, linhas_dict, relatorio, i):
        self._log(f"🤖 Consultando IA: {nome}")
        try:
            self._enriquecer_para_n8n(dados)
            payload = {"arquivo": nome, "modo": "extract",
                       "dados_parciais": dados, "conteudo_xml": conteudo,
                       "descricoes": _bundle_descricoes(dados)}
            r = chamar_n8n(payload)
            js = _parse_json_safe(r)

            manual_review, motivo = self._detectar_manual_review(js)
            if manual_review:
                self._log(f"⚠️ Esta nota requer atenção manual: {nome}")
                if motivo:
                    self._log(f"   Motivo: {motivo}")
                relatorio.append(_relatorio_row(nome, dados, "Manual Review", "extract", motivo))
                return

            res_ia = r.text.strip()
            if res_ia.startswith("2;") or res_ia.startswith("4;"):
                partes = res_ia.split(";")
                _lc_ia = normalize_digits(partes[19]) if len(partes) > 19 else ""
                if not item_lc_valido(_lc_ia):
                    self._log(f"⚠️ Classificação do serviço inválida, nota ignorada: {nome}")
                    relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", f"Item LC inválido: {_lc_ia}"))
                else:
                    res_ia = self._normalizar_linha_extract(res_ia, dados)
                    chave = f"{partes[1]}_{partes[7]}" if len(partes) > 7 else f"{nome}_{i}"
                    linhas_dict[chave] = res_ia
                    self._log(f"✅ Nota processada: {nome}")
                    relatorio.append(_relatorio_row(nome, dados, "OK", "extract", "IA sucesso"))
            else:
                self._log(f"⚠️ Nota não pôde ser processada: {nome}")
                relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", "Resposta inesperada"))
        except Exception as e:
            self._log(f"❌ Erro ao processar nota {nome}: {e}")
            relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", str(e)))

    def _processar_ia_extract_incompleto(self, nome, conteudo, dados, linhas_dict, relatorio, i):
        try:
            self._enriquecer_para_n8n(dados)
            payload = {"arquivo": nome, "modo": "extract",
                       "dados_parciais": dados, "conteudo_xml": conteudo,
                       "descricoes": _bundle_descricoes(dados)}
            r = chamar_n8n(payload)
            js = _parse_json_safe(r)

            if isinstance(js, list) and js:
                obj = js[0]
                if obj.get("status") == "manual_fill_itemlc_ddd":
                    self._log(f"⚠️ Classificação do serviço não encontrada automaticamente: {nome}")
                    dados_manual = self._preparar_dados_manual_n8n(obj, dados)
                    dados_manual["_xml_content"] = conteudo
                    linha_manual = self._abrir_tela_manual(dados_manual, nome, from_n8n=True)
                    if linha_manual:
                        linhas_dict[nome.replace(".xml", "")] = linha_manual
                        self._log(f"✅ Nota preenchida manualmente: {nome}")
                        relatorio.append(_relatorio_row(nome, dados, "OK", "extract", "Preenchimento manual"))
                    else:
                        relatorio.append(_relatorio_row(nome, dados, "Cancelado", "extract", "Manual cancelado"))
                    return

            res_ia = r.text.strip()
            if res_ia.startswith("2;") or res_ia.startswith("4;"):
                partes = res_ia.split(";")
                _lc_ia = normalize_digits(partes[19]) if len(partes) > 19 else ""
                if not item_lc_valido(_lc_ia):
                    self._log(f"⚠️ Classificação do serviço inválida, nota ignorada: {nome}")
                    relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", f"Item LC inválido: {_lc_ia}"))
                else:
                    res_ia = self._normalizar_linha_extract(res_ia, dados)
                    chave = f"{partes[1]}_{partes[7]}" if len(partes) > 7 else f"{nome}_{i}"
                    linhas_dict[chave] = res_ia
                    self._log(f"✅ Nota processada: {nome}")
                    relatorio.append(_relatorio_row(nome, dados, "OK", "extract", "IA sucesso"))
            else:
                self._log(f"⚠️ Nota não pôde ser processada: {nome}")
                relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", "Resposta inesperada"))
        except Exception as e:
            self._log(f"❌ Erro ao processar nota {nome}: {e}")
            relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", str(e)))

    def _processar_goiania(self, nome, conteudo, dados, linhas_dict, relatorio):
        if not self._gerar_mei:
            self._log(f"⏭ Nota de Goiânia ignorada (MEI desativado): {nome}")
            relatorio.append(_relatorio_row(nome, dados, "Ignorada", "local", "MEI desativado"))
            return

        if not dados.get("eh_mei", False):
            self._log(f"⏭ Nota de Goiânia não elegível, ignorada: {nome}")
            relatorio.append(_relatorio_row(nome, dados, "Ignorada", "local", "Goiânia não-MEI"))
            return

        ddd = GOIANIA_DDD
        item_lc = normalize_digits(dados.get("item_lc_final", ""))
        if item_lc:
            item_lc = item_lc[:4].zfill(4)

        # Aceita LC 01-40 OU grupo 99 (sem incidencia) — mesma regra do map_only
        _lc_ok = item_lc and (item_lc_valido(item_lc) or item_lc.startswith("99"))
        if not _lc_ok:
            _debug_log(
                f"[goiania-nolc] {nome} | item_lc={item_lc!r} "
                f"c_trib_nac={dados.get('c_trib_nac','')!r}"
            )
            self._log(f"🤖 Consultando IA para classificar serviço: {nome}")
            try:
                payload_ext = {"arquivo": nome, "modo": "extract",
                               "dados_parciais": dados, "conteudo_xml": conteudo,
                               "descricoes": _bundle_descricoes(dados)}
                r_ext = chamar_n8n(payload_ext)
                js_ext = _parse_json_safe(r_ext)

                if isinstance(js_ext, list) and js_ext:
                    obj_ext = js_ext[0]
                    if obj_ext.get("status") == "manual_fill_itemlc_ddd":
                        self._log(f"⚠️ Classificação do serviço não encontrada automaticamente: {nome}")
                        dados_manual = self._preparar_dados_manual_n8n(obj_ext, dados)
                        dados_manual["_xml_content"] = conteudo
                        linha_manual = self._abrir_tela_manual(dados_manual, nome, from_n8n=True)
                        if linha_manual:
                            linhas_dict[f"{dados['numero']}_{dados['cnpj_p']}"] = linha_manual
                            self._log(f"✅ Nota preenchida manualmente: {nome}")
                            relatorio.append(_relatorio_row(nome, dados, "OK", "extract", "LC manual (Goiânia)"))
                        else:
                            relatorio.append(_relatorio_row(nome, dados, "Cancelado", "extract", "LC cancelado"))
                        return

                res_ext = r_ext.text.strip()
                _lc_ext_ok = False
                if res_ext.startswith("2;") or res_ext.startswith("4;"):
                    partes = res_ext.split(";")
                    _lc_ext = normalize_digits(partes[19]) if len(partes) > 19 else ""
                    if item_lc_valido(_lc_ext):
                        res_ext = self._normalizar_linha_extract(res_ext, dados)
                        chave = f"{partes[1]}_{partes[7]}" if len(partes) > 7 else f"{dados['numero']}_{dados['cnpj_p']}"
                        linhas_dict[chave] = res_ext
                        self._log(f"✅ Nota processada: {nome}")
                        relatorio.append(_relatorio_row(nome, dados, "OK", "extract", "LC extraído pela IA"))
                        _lc_ext_ok = True
                    else:
                        self._log(f"⚠️ Classificação do serviço inválida: {nome}")

                if not _lc_ext_ok:
                    self._log(f"⚠️ Necessário preenchimento manual: {nome}")
                    dados_manual = {
                        "item_lc_original": dados.get("descricao_servico", "") or dados.get("item_lc_final", ""),
                        "codigo_municipio": dados.get("codigo_municipio", ""),
                    }
                    dados_manual.update(dados)
                    dados_manual["_xml_content"] = conteudo
                    linha_manual = self._abrir_tela_manual(dados_manual, nome, from_n8n=False)
                    if linha_manual:
                        linhas_dict[f"{dados['numero']}_{dados['cnpj_p']}"] = linha_manual
                        self._log(f"✅ Nota preenchida manualmente: {nome}")
                        relatorio.append(_relatorio_row(nome, dados, "OK", "local", "LC manual"))
                    else:
                        relatorio.append(_relatorio_row(nome, dados, "Cancelado", "local", "LC cancelado"))
            except Exception as e_ext:
                self._log(f"❌ Erro ao processar nota {nome}: {e_ext}")
                relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", str(e_ext)))
            return

        linha = montar_linha_txt(dados, ddd=ddd, item_lc=item_lc, empresa_ibge=self._empresa_ibge)
        linhas_dict[f"{dados['numero']}_{dados['cnpj_p']}"] = linha
        self._log(f"✅ Nota processada: {nome}")
        relatorio.append(_relatorio_row(nome, dados, "OK", "local", "Goiânia"))

    def _processar_map_only(self, nome, conteudo, dados, linhas_dict, relatorio, i):
        cep = normalize_digits(dados.get("cep", ""))
        # Consulta CEP localmente (substitui chamada antes feita pelo n8n).
        ddd_cep = _enriquecer_dados_via_cep(dados)
        # Consulta CNPJ apenas para prestador fora de Goiânia quando o XML
        # não trouxe regime tributário (tag opSimpNac/OptanteSimplesNacional).
        _enriquecer_optante_via_cnpj(dados)

        # Fast-path: se o XML já trouxe um item LC válido (item_lc_final) e o
        # ViaCEP nos deu um DDD, não há necessidade de consultar o n8n.
        # Equivalente ao Code node "Validar Código LC" + IF "Tem Código Válido?"
        # do workflow, executados antes do request HTTP.
        _lc_local = normalize_digits(dados.get("item_lc_final", ""))[:4]
        # Aceita LC valido (01-40) OU grupo 99 (servicos sem incidencia ISSQN).
        # Grupo 99 e categoria oficial da NFS-e Nacional; portal aceita '9901'.
        _lc_ok = _lc_local and ddd_cep and (
            item_lc_valido(_lc_local) or _lc_local.startswith("99")
        )
        if _lc_ok:
            _lc_local = _lc_local.zfill(4)
            linha = montar_linha_txt(dados, ddd=ddd_cep, item_lc=_lc_local, empresa_ibge=self._empresa_ibge)
            linhas_dict[f"{dados['numero']}_{dados['cnpj_p']}"] = linha
            self._log(f"✅ Nota processada (local — LC válido no XML): {nome}")
            relatorio.append(_relatorio_row(
                nome, dados, "OK", "local", f"DDD={ddd_cep} LC={_lc_local}"
            ))
            return

        # Log de por que fast-path falhou (terminal-only, nao polui painel UI)
        _debug_log(
            f"[fastpath-fail] {nome} | lc_local={_lc_local!r} "
            f"ddd_cep={ddd_cep!r} lc_xml={dados.get('item_lc_final','')!r} "
            f"c_trib_nac={dados.get('c_trib_nac','')!r} "
            f"cep={dados.get('cep','')!r}"
        )

        self._log(f"🤖 Consultando IA: {nome}")
        try:
            payload = {
                "arquivo": nome, "modo": "map_only",
                "dados_parciais": {**dados, "codigo_municipio": None},
                "conteudo_xml": conteudo,
                "descricoes": _bundle_descricoes(dados),
            }
            r = chamar_n8n(payload)
            js = _parse_json_safe(r)
            n8n_obj = _extrair_n8n_obj(js, r.text if js is None else "")

            _status_n8n = (n8n_obj or {}).get("status", "")
            if _status_n8n == "manual_review_map_only":
                self._log(f"⚠️ Preenchimento manual necessário: {nome}")
                ddd_n8n = normalize_digits(str((n8n_obj or {}).get("ddd", "") or ""))[:2]
                dados_manual = self._montar_dados_manual(dados, n8n_obj, ddd_n8n)
                dados_manual["_xml_content"] = conteudo
                linha_manual = self._abrir_tela_manual(dados_manual, nome, from_n8n=True)
                if linha_manual:
                    linhas_dict[nome.replace(".xml", "")] = linha_manual
                    self._log(f"✅ Nota preenchida manualmente: {nome}")
                    relatorio.append(_relatorio_row(nome, dados, "OK", "map_only", "Manual (review)"))
                else:
                    relatorio.append(_relatorio_row(nome, dados, "Cancelado", "map_only", "Manual cancelado"))
                return

            ddd, item_lc = _extrair_ddd_itemlc(n8n_obj)

            if not ddd or not item_lc:
                txt = (r.text or "").strip()
                if ";" in txt:
                    parts = [p.strip() for p in txt.split(";")]
                    if len(parts) >= 2:
                        ddd, item_lc = parts[0], parts[1]

            ddd = normalize_digits(ddd)[:2]
            item_lc = normalize_digits(item_lc)

            # Fallback DDD: se o n8n não devolveu, usa o que veio do ViaCEP local.
            if not ddd:
                ddd = ddd_cep

            # Fallback LC: se o n8n devolveu vazio mas o XML tinha LC válido em
            # item_lc_final, usar o local. Evita sobrescrever bom-dado com vazio
            # quando a IA falha (baixa confiança, timeout, etc).
            if not item_lc:
                _lc_xml = normalize_digits(dados.get("item_lc_final", ""))[:4]
                if _lc_xml and item_lc_valido(_lc_xml):
                    item_lc = _lc_xml
                    self._log(f"   ↪ usando LC do XML como fallback ({item_lc})")

            _lc_invalido = item_lc and len(item_lc) == 4 and not item_lc_valido(item_lc)
            if _lc_invalido:
                self._processar_map_only_retry(
                    nome, conteudo, dados, cep, item_lc, ddd, n8n_obj,
                    linhas_dict, relatorio
                )
                return

            if n8n_obj:
                self._aplicar_dados_n8n(dados, n8n_obj)

            linha = montar_linha_txt(dados, ddd=ddd, item_lc=item_lc, empresa_ibge=self._empresa_ibge)
            linhas_dict[f"{dados['numero']}_{dados['cnpj_p']}"] = linha
            self._log(f"✅ Nota processada: {nome}")
            relatorio.append(_relatorio_row(nome, dados, "OK", "map_only", f"DDD={ddd} LC={item_lc}"))

        except Exception as e:
            self._log(f"❌ Erro ao processar nota {nome}: {e}")
            relatorio.append(_relatorio_row(nome, dados, "Erro", "map_only", str(e)))

    def _processar_map_only_retry(self, nome, conteudo, dados, cep, item_lc_orig, ddd_orig,
                                   n8n_obj, linhas_dict, relatorio):
        self._log(f"🔄 Classificação inconsistente, tentando novamente: {nome}")
        try:
            # CEP já foi consultado localmente em _processar_map_only — `dados`
            # já está enriquecido. n8n não precisa mais do campo cep.
            payload_retry = {
                "arquivo": nome, "modo": "map_only",
                "item_lc_invalido": item_lc_orig,
                "dados_parciais": {**dados, "codigo_municipio": None},
                "conteudo_xml": conteudo,
                "descricoes": _bundle_descricoes(dados),
            }
            r2 = chamar_n8n(payload_retry)
            js2 = _parse_json_safe(r2)
            n8n2 = _extrair_n8n_obj(js2)

            ddd2 = item_lc2 = ""
            if n8n2:
                ddd2 = normalize_digits(str(n8n2.get("DDD", "")).strip())[:2]
                item_lc2 = normalize_digits(str(n8n2.get("itemLC", "")).strip())

            if len(ddd2) == 2 and len(item_lc2) == 4 and item_lc_valido(item_lc2):
                if n8n2:
                    self._aplicar_dados_n8n(dados, n8n2)
                linha = montar_linha_txt(dados, ddd=ddd2, item_lc=item_lc2, empresa_ibge=self._empresa_ibge)
                linhas_dict[f"{dados['numero']}_{dados['cnpj_p']}"] = linha
                self._log(f"✅ Nota processada: {nome}")
                relatorio.append(_relatorio_row(nome, dados, "OK", "map_only", f"LC retry: {item_lc2}"))
            else:
                self._log(f"⚠️ Necessário preenchimento manual: {nome}")
                ddd_fb = ddd2 or ddd_orig or normalize_digits(str((n8n_obj or {}).get("ddd", "") or ""))[:2]
                dados_manual = self._montar_dados_manual(dados, n8n_obj, ddd_fb)
                dados_manual["_xml_content"] = conteudo
                chave_nf = nome.replace(".xml", "")
                linha_manual = self._abrir_tela_manual(dados_manual, chave_nf, from_n8n=True)
                if linha_manual:
                    linhas_dict[chave_nf] = linha_manual
                    self._log(f"✅ Nota preenchida manualmente: {chave_nf}")
                    relatorio.append(_relatorio_row(nome, dados, "OK", "map_only", "Manual após retry"))
                else:
                    relatorio.append(_relatorio_row(nome, dados, "Cancelado", "map_only", "Manual cancelado"))
        except Exception as e_retry:
            self._log(f"❌ Erro ao processar nota {nome}: {e_retry}")
            relatorio.append(_relatorio_row(nome, dados, "Erro", "map_only", str(e_retry)))

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _detectar_manual_review(js) -> tuple[bool, str]:
        """Detecta se a resposta N8N indica manual_review."""
        if isinstance(js, dict) and js.get("status") == "manual_review":
            return True, js.get("motivo", "")
        if isinstance(js, list) and js:
            obj = js[0]
            if isinstance(obj, dict):
                msg = obj.get("Mensagem_erro_1")
                if msg:
                    try:
                        inner = json.loads(msg) if isinstance(msg, str) else msg
                        if inner.get("status") == "manual_review":
                            return True, inner.get("motivo", "")
                    except (ValueError, TypeError):
                        pass
        return False, ""

    @staticmethod
    def _normalizar_linha_extract(linha: str, dados: dict) -> str:
        """Garante que linha vinda do n8n tenha os 23 campos do novo layout ISSNet.

        Workflows n8n antigos retornam 21 campos. Esta função preserva a linha
        original e apenas anexa local_prestacao + optante_sn_mei a partir de
        `dados` quando faltantes.
        """
        l = linha.rstrip()
        # remover ';' finais para contar
        while l.endswith(";"):
            l = l[:-1]
        partes = l.split(";")
        if len(partes) >= 23:
            return ";".join(partes) + ";"
        while len(partes) < 21:
            partes.append("")
        local_prest = normalize_digits(str(dados.get("local_prestacao", "") or ""))
        optante = str(dados.get("optante_sn_mei", "1") or "1")
        if optante not in ("1", "2", "3"):
            optante = "1"
        partes.append(local_prest)
        partes.append(optante)
        return ";".join(partes) + ";"

    @staticmethod
    def _preparar_dados_manual_n8n(obj_n8n: dict, dados: dict) -> dict:
        """Prepara dados_manual a partir de resposta N8N para preenchimento manual."""
        dados_manual = obj_n8n.get("dados_extraidos", {})
        if not (dados_manual.get("item_lc_original") or "").strip():
            dados_manual["item_lc_original"] = (
                str(obj_n8n.get("item_lc_original", "") or "").strip()
                or dados.get("descricao_servico", "")
                or dados.get("item_lc_final", "")
            )
        if not (dados_manual.get("codigo_municipio") or "").strip():
            dados_manual["codigo_municipio"] = dados.get("codigo_municipio", "")
        # Tags brutas extraidas do XML para exibicao no dialogo de fallback
        for k in ("x_desc_serv", "discriminacao", "c_trib_nac", "x_trib_nac", "x_nbs"):
            if not (dados_manual.get(k) or "").strip():
                dados_manual[k] = dados.get(k, "")
        # Emitente (prestador) — exibido discretamente no diálogo de fallback
        if not (dados_manual.get("cpf_cnpj") or "").strip():
            dados_manual["cpf_cnpj"] = dados.get("cnpj_p", "")
        if not (dados_manual.get("razao_social") or "").strip():
            dados_manual["razao_social"] = dados.get("razao_p", "")
        return dados_manual

    @staticmethod
    def _aplicar_dados_n8n(dados: dict, n8n_obj: dict):
        """Aplica dados de endereço do N8N apenas como fallback.

        A consulta de CEP agora é feita localmente via ViaCEP (services/cep.py),
        então `dados` já vem enriquecido. Só sobrescrevemos campos vazios para
        manter compat com workflows n8n que ainda devolvam endereço.
        """
        for campo_n8n, campo_dados in [
            ("estado", "uf"), ("logradouro", "endereco"),
            ("numero_end", "numero_end"), ("bairro", "bairro"),
        ]:
            val = str(n8n_obj.get(campo_n8n, "") or "").strip()
            if val and not (dados.get(campo_dados) or "").strip():
                dados[campo_dados] = val
        cidade_n8n = str(n8n_obj.get("cidade", "") or "").strip()
        if cidade_n8n and not (dados.get("cidade_override") or "").strip():
            dados["cidade_override"] = cidade_n8n

    def _montar_dados_manual(self, dados, n8n_obj, ddd):
        return {
            "modelo": "2" if eh_goiania(dados) else "4",
            "numero_documento": dados.get("numero", ""),
            "valor_tributavel": dados.get("vlr_trib", ""),
            "valor_documento": dados.get("vlr_doc", ""),
            "aliquota": dados.get("aliq_val", "0"),
            "data_emissao": dados.get("dt_fmt", ""),
            "data_pagamento": dados.get("dt_fmt", ""),
            "cpf_cnpj": dados.get("cnpj_p", ""),
            "razao_social": dados.get("razao_p", ""),
            "inscricao_municipal": dados.get("im_p", "") if eh_goiania(dados) else "",
            "imposto_retido": dados.get("iss_ret", "2"),
            "iss_ret_origem": dados.get("iss_ret_origem", "abrasf"),
            "cep": dados.get("cep", ""),
            "endereco": dados.get("endereco", ""),
            "numero": dados.get("numero_end", ""),
            "bairro": str((n8n_obj or {}).get("bairro", "") or "").strip() or dados.get("bairro", ""),
            "cidade": str((n8n_obj or {}).get("cidade", "") or "").strip() or consulta_cidade_ibge(dados.get("codigo_municipio", "")),
            "estado": str((n8n_obj or {}).get("estado", "") or "").strip() or dados.get("uf", ""),
            "tributado_municipio": "1" if eh_goiania(dados) else "0",
            "unidade_economica": "0",
            "ddd": ddd,
            "municipio": str((n8n_obj or {}).get("localidade", "") or "").strip(),
            "item_lc_original": (
                str((n8n_obj or {}).get("item_lc_original", "") or "").strip()
                or dados.get("descricao_servico", "")
                or dados.get("item_lc_final", "")
            ),
            "x_desc_serv": dados.get("x_desc_serv", ""),
            "discriminacao": dados.get("discriminacao", ""),
            "c_trib_nac": dados.get("c_trib_nac", ""),
            "x_trib_nac": dados.get("x_trib_nac", ""),
            "x_nbs": dados.get("x_nbs", ""),
            "local_prestacao": dados.get("local_prestacao", ""),
            "optante_sn_mei": dados.get("optante_sn_mei", "1"),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Vigência, validação e cabeçalho
    # ──────────────────────────────────────────────────────────────────────────

    # Aceita notas emitidas ate MAX_MESES_ATRAS antes da vigencia selecionada.
    # Ex: processando 062026 com valor 1 -> aceita 052026 e 062026.
    # Notas mais antigas sao DESCARTADAS totalmente (nem gera arquivo separado).
    # Objetivo: evitar ruido de notas muito antigas que aparecem por atualizacao
    # tardia na Autmais mas nao serao lancadas retroativamente.
    MAX_MESES_ATRAS = 1

    def _filtrar_vigencia(self, linhas_dict, vigencia, emp_cod):
        notas_vig_errada = {}
        descartadas_antigas = {}
        chaves_remover = []

        # Calcula lista de vigencias aceitas como "atraso": vig e vig-1..vig-MAX
        vigencias_aceitas_atraso = set()
        try:
            mes_atual = int(vigencia[:2])
            ano_atual = int(vigencia[2:])
            for k in range(1, self.MAX_MESES_ATRAS + 1):
                m = mes_atual - k
                a = ano_atual
                if m <= 0:
                    m += 12
                    a -= 1
                vigencias_aceitas_atraso.add(f"{m:02d}{a:04d}")
        except (ValueError, IndexError):
            pass

        for chave, linha in linhas_dict.items():
            partes = linha.split(";")
            if len(partes) > 5 and len(partes[5]) == 8:
                vig_nota = partes[5][2:]
                if vig_nota and vig_nota != vigencia:
                    if vig_nota in vigencias_aceitas_atraso:
                        notas_vig_errada.setdefault(vig_nota, []).append(linha)
                    else:
                        # Muito antiga -> descarta silenciosamente (com log)
                        descartadas_antigas.setdefault(vig_nota, 0)
                        descartadas_antigas[vig_nota] += 1
                    chaves_remover.append(chave)
        for chave in chaves_remover:
            del linhas_dict[chave]
        if notas_vig_errada:
            total_div = sum(len(v) for v in notas_vig_errada.values())
            self._log(f"⚠️ {total_div} nota(s) com data de emissão fora da vigência {vigencia}:")
            for vig, lins in notas_vig_errada.items():
                self._log(f"   → {len(lins)} nota(s) de {vig[:2]}/{vig[2:]} → arquivo {emp_cod}_{vig}.txt")
            self._log("   Esses arquivos serão criados automaticamente ao salvar.")
        if descartadas_antigas:
            total_ant = sum(descartadas_antigas.values())
            self._log(f"🗑 {total_ant} nota(s) muito antiga(s) descartada(s) (>{self.MAX_MESES_ATRAS} mês(es) antes de {vigencia}):")
            for vig, qtd in descartadas_antigas.items():
                self._log(f"   → {qtd} de {vig[:2]}/{vig[2:]}")
        return notas_vig_errada

    def _validar_tomador_goiania(self, dict_xmls: dict) -> bool:
        """Verifica se ao menos uma nota tem tomador de município aceito."""
        mun_encontrados = set()
        for conteudo in dict_xmls.values():
            try:
                root = ET.fromstring(conteudo)
                _, _, _, mun, _ = extrair_cabecalho_info(root)
                mun_norm = normalize_digits(mun)
                if not mun_norm:
                    continue
                if eh_municipio_aceito(mun_norm):
                    return True
                mun_encontrados.add(mun_norm)
            except ET.ParseError:
                continue
        if mun_encontrados:
            self._log(f"❌ O tomador das notas não é de um município aceito (encontrados: {', '.join(mun_encontrados)}).")
            return False
        return True

    def _eh_tomador_goiania(self, mun_tomador: str) -> bool:
        return eh_municipio_aceito(mun_tomador)

    def _gerar_cabecalho(self, dict_xmls, emp_cod: str = "", vigencia: str = ""):
        im_tomador = razao_tomador = data_emissao = cnpj_tomador = ""
        # 1ª passada: ABRASF com tomador aceito e IM
        for conteudo in dict_xmls.values():
            try:
                root = ET.fromstring(conteudo)
                if detectar_padrao_nfse(root) == "abrasf":
                    im, razao, dt, mun, cnpj = extrair_cabecalho_info(root)
                    if im and self._eh_tomador_goiania(mun):
                        im_tomador, razao_tomador, data_emissao, cnpj_tomador = im, razao, dt, cnpj
                        break
            except ET.ParseError:
                continue
        # 2ª passada: qualquer nota com tomador aceito
        if not im_tomador:
            for conteudo in dict_xmls.values():
                try:
                    root = ET.fromstring(conteudo)
                    im, razao, dt, mun, cnpj = extrair_cabecalho_info(root)
                    if not self._eh_tomador_goiania(mun):
                        continue
                    if not im_tomador and im:
                        im_tomador = im
                    if not razao_tomador and razao:
                        razao_tomador = razao
                    if not data_emissao and dt:
                        data_emissao = dt
                    if not cnpj_tomador and cnpj:
                        cnpj_tomador = cnpj
                    if im_tomador and razao_tomador and data_emissao and cnpj_tomador:
                        break
                except ET.ParseError:
                    continue
        # 3ª passada: fallback da planilha se IM/razão não encontrados no XML
        if (not im_tomador or not razao_tomador) and emp_cod:
            try:
                info = get_company_info(emp_cod)
                if info:
                    if not im_tomador and info.get("im"):
                        im_tomador = info["im"]
                    if not razao_tomador and info.get("razao"):
                        razao_tomador = info["razao"]
            except Exception:
                pass
        # Garantir CNPJ tomador mesmo sem tomador aceito
        if not cnpj_tomador:
            for conteudo in dict_xmls.values():
                try:
                    root = ET.fromstring(conteudo)
                    _, _, _, _, cnpj = extrair_cabecalho_info(root)
                    if cnpj:
                        cnpj_tomador = cnpj
                        break
                except ET.ParseError:
                    continue

        # Mês/Ano do cabeçalho SEMPRE vêm da vigência selecionada (mmaaaa),
        # não da data de emissão de uma nota qualquer. Garante que reimportações
        # de notas atrasadas não bagunçam a competência declarada.
        vig = normalize_digits(vigencia)
        if len(vig) == 6:
            data_emissao = f"{vig[2:]}-{vig[:2]}-01T00:00:00"
        # Fallback: se vigência inválida, mantém o que veio das notas
        cabecalho = montar_cabecalho(im_tomador, razao_tomador, data_emissao)
        return im_tomador, razao_tomador, cabecalho, cnpj_tomador

    # ──────────────────────────────────────────────────────────────────────────
    # Relatório
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _enriquecer_relatorio(relatorio, linhas_txt, chave_map, ts_map):
        txt_lines_map = {}
        for idx, l in enumerate(linhas_txt, 1):
            p = l.split(";")
            if len(p) > 7:
                txt_lines_map[f"{p[1].strip()}_{p[7].strip()}"] = str(idx)

        for row in relatorio:
            del row[7:]
            row.append(chave_map.get(row[0], ""))
            row.append(ts_map.get(row[0], ""))
            if len(row) > 4 and row[4] == "OK":
                row.append(txt_lines_map.get(f"{str(row[2]).strip()}_{str(row[1]).strip()}", "-"))
            else:
                row.append("-")

    @staticmethod
    def _enriquecer_relatorio_vazio(relatorio, chave_map, ts_map):
        for row in relatorio:
            del row[7:]
            row.append(chave_map.get(row[0], ""))
            row.append(ts_map.get(row[0], ""))
            row.append("-")
