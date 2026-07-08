import xml.etree.ElementTree as ET
from datetime import datetime

from core.xml_parser import find_text, detectar_padrao_nfse
from core.validators import normalize_digits, has_value, item_lc_valido
from core.formatters import formatar_aliquota


def extrair_dados_python(xml_string):
    try:
        root = ET.fromstring(xml_string)
        padrao = detectar_padrao_nfse(root)

        # Municipio do PRESTADOR (usado para decidir modelo=2/4 vs empresa tomadora).
        # NUNCA cair em Tomador/MunicipioIncidencia/cLocPrestacao — sao locais
        # diferentes e vazam IM+modelo errado no TXT ISSNet.
        codigo_municipio = find_text(root, [
            # ABRASF 2.04
            ".//{*}PrestadorServico//{*}Endereco//{*}CodigoMunicipio",
            ".//{*}Prestador//{*}Endereco//{*}CodigoMunicipio",
            # NFS-e Nacional (SPED) — emitente
            ".//{*}emit//{*}enderNac//{*}cMun",
            ".//{*}emit//{*}enderNac//{*}CodigoMunicipio",
            # OrgaoGerador = municipio emissor da NFSe (fallback razoavel — prestador)
            ".//{*}InfNfse//{*}OrgaoGerador//{*}CodigoMunicipio",
            ".//{*}OrgaoGerador//{*}CodigoMunicipio",
        ], default="")

        _cep_raw = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Cep",
            ".//{*}Prestador//{*}Endereco//{*}Cep",
            ".//{*}emit//{*}enderNac//{*}CEP",
        ], default="")
        cep = normalize_digits(_cep_raw).zfill(8) if _cep_raw else ""

        endereco = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Endereco",
            ".//{*}Prestador//{*}Endereco//{*}Endereco",
            ".//{*}emit//{*}enderNac//{*}xLgr",
        ], default="")

        numero_end = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Numero",
            ".//{*}Prestador//{*}Endereco//{*}Numero",
            ".//{*}emit//{*}enderNac//{*}nro",
        ], default="")

        bairro = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Bairro",
            ".//{*}Prestador//{*}Endereco//{*}Bairro",
            ".//{*}emit//{*}enderNac//{*}xBairro",
        ], default="")

        numero = find_text(root, [
            ".//{*}CompNfse//{*}Nfse//{*}InfNfse//{*}Numero",
            ".//{*}Nfse//{*}InfNfse//{*}Numero",
            ".//{*}InfNfse//{*}Numero",
            ".//{*}infNFSe//{*}nNFSe",
            ".//{*}nNFSe",
            ".//{*}nDFSe",
            ".//{*}nDPS",
        ], default="")

        # Número alternativo (nDPS) — usado quando o número principal estoura
        # o limite de caracteres do portal DMST-e (>9 dígitos).
        numero_dps = find_text(root, [
            ".//{*}infDPS//{*}nDPS",
            ".//{*}DPS//{*}infDPS//{*}nDPS",
            ".//{*}nDPS",
        ], default="")

        cnpj_p = find_text(root, [
            ".//{*}Prestador//{*}Cnpj",
            ".//{*}PrestadorServico//{*}IdentificacaoPrestador//{*}CpfCnpj//{*}Cnpj",
            ".//{*}IdentificacaoPrestador//{*}CpfCnpj//{*}Cnpj",
            ".//{*}emit//{*}CNPJ",
            ".//{*}prest//{*}CNPJ",
        ], default="")

        im_p = find_text(root, [
            ".//{*}Prestador//{*}InscricaoMunicipal",
            ".//{*}PrestadorServico//{*}IdentificacaoPrestador//{*}InscricaoMunicipal",
            ".//{*}IdentificacaoPrestador//{*}InscricaoMunicipal",
            ".//{*}emit//{*}IM",
            ".//{*}prest//{*}IM",
        ], default="")

        razao_p = find_text(root, [
            ".//{*}PrestadorServico//{*}RazaoSocial",
            ".//{*}Prestador//{*}RazaoSocial",
            ".//{*}RazaoSocial",
            ".//{*}emit//{*}xNome",
        ], default="")

        vlr_doc = find_text(root, [
            ".//{*}Servico//{*}Valores//{*}ValorServicos",
            ".//{*}Servico//{*}ValoresServico//{*}ValorServicos",
            ".//{*}vServPrest//{*}vServ",
            ".//{*}ValoresNfse//{*}ValorServicos",
            ".//{*}ValorServicos",
            ".//{*}vServ",
            ".//{*}ValoresNfse//{*}ValorLiquidoNfse",
            ".//{*}ValorLiquidoNfse",
            ".//{*}valores//{*}vLiq",
            ".//{*}valores//{*}vBC",
        ], default="")

        vlr_trib = find_text(root, [
            ".//{*}ValoresNfse//{*}BaseCalculo",
            ".//{*}Servico//{*}Valores//{*}BaseCalculo",
            ".//{*}BaseCalculo",
            ".//{*}valores//{*}vBC",
        ], default="")

        aliq_val = find_text(root, [
            ".//{*}ValoresNfse//{*}Aliquota",
            ".//{*}Servico//{*}Valores//{*}Aliquota",
            ".//{*}Aliquota",
            ".//{*}pAliqAplic",
            ".//{*}tribMun//{*}pAliq",
        ], default="0")

        try:
            _aliq_num = float((aliq_val or "0").replace(",", "."))
        except ValueError:
            _aliq_num = 0.0

        if _aliq_num == 0:
            valor_iss = find_text(root, [
                ".//{*}Servico//{*}Valores//{*}ValorIss",
                ".//{*}ValoresNfse//{*}ValorIss",
                ".//{*}ValorIss",
                ".//{*}tribMun//{*}vTribMun",
                ".//{*}vRecTrib",
            ], default="")
            try:
                _iss = float((valor_iss or "0").replace(",", "."))
                _base = float((vlr_trib or vlr_doc or "0").replace(",", "."))
                if _iss > 0 and _base > 0:
                    aliq_val = str(round((_iss / _base) * 100, 2))
            except (ValueError, ZeroDivisionError):
                pass

        aliq_val = formatar_aliquota(aliq_val)

        iss_ret = find_text(root, [
            ".//{*}Servico//{*}IssRetido",
            ".//{*}IssRetido",
        ], default="")
        iss_ret_origem = "abrasf"

        if not iss_ret:
            iss_ret = find_text(root, [
                ".//{*}tribMun//{*}tpRetISSQN",
                ".//{*}tpRetISSQN",
            ], default="1")
            iss_ret_origem = "nacional"

        item_lista_servico = find_text(root, [
            ".//{*}Servico//{*}ItemListaServico",
            ".//{*}ItemListaServico",
        ], default="")

        ctribnac = find_text(root, [
            ".//{*}cServ//{*}cTribNac",
            ".//{*}cTribNac",
        ], default="")

        xtribnac = find_text(root, [
            ".//{*}cServ//{*}xTribNac",
            ".//{*}xTribNac",
        ], default="").strip()

        xtribmun = find_text(root, [
            ".//{*}cServ//{*}xTribMun",
            ".//{*}xTribMun",
        ], default="").strip()

        xnbs = find_text(root, [
            ".//{*}cServ//{*}xNBS",
            ".//{*}xNBS",
        ], default="").strip()

        x_desc_serv_raw = find_text(root, [
            ".//{*}cServ//{*}xDescServ",
            ".//{*}xDescServ",
        ], default="").strip()

        discriminacao_raw = find_text(root, [
            ".//{*}Servico//{*}Discriminacao",
            ".//{*}Discriminacao",
        ], default="").strip()

        # Mantém prioridade legada (Discriminacao > xDescServ) para descricao_servico,
        # mas as tags brutas vao para o dict separadamente.
        descricao_servico = discriminacao_raw or x_desc_serv_raw

        ctribnac = normalize_digits(ctribnac)
        item_lc_final = ""

        # Escolhe a melhor descrição tributária disponível:
        # xTribNac é descartado quando contém "(VETADO)" ou "sem a incidência"
        _xtribnac_lower = xtribnac.lower() if xtribnac else ""
        _xtribnac_vetado = (
            not xtribnac
            or "vetado" in _xtribnac_lower
            or "sem a incidência" in _xtribnac_lower
            or "sem a incidencia" in _xtribnac_lower
        )
        _desc_trib = xtribnac if not _xtribnac_vetado else (xtribmun or xtribnac)

        if item_lista_servico:
            item_lc_final = normalize_digits(item_lista_servico)[:4]
        elif ctribnac:
            if _desc_trib:
                item_lc_final = f"{ctribnac} - {_desc_trib}"
            else:
                item_lc_final = normalize_digits(ctribnac)

        # Grupo 99 (Servicos sem incidencia ISSQN/ICMS) — categoria oficial
        # da NFS-e Nacional. item_lc_valido() rejeita (so aceita 01-40) mas
        # portal ISSNet aceita "9901". Preserva 9901 pra evitar chamada IA
        # desnecessaria no fast-path map_only.
        if item_lc_final:
            _digitos = normalize_digits(item_lc_final)
            if _digitos.startswith("99"):
                item_lc_final = "9901"
            elif not item_lc_valido(item_lc_final):
                item_lc_final = ""

        # Descrição do serviço: prefere xTribNac (se útil) > xTribMun > Discriminação
        _xtribnac_util = xtribnac if not _xtribnac_vetado else ""
        descricao_servico = _xtribnac_util or xtribmun or descricao_servico

        uf = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Uf",
            ".//{*}Prestador//{*}Endereco//{*}Uf",
            ".//{*}Uf",
            ".//{*}emit//{*}enderNac//{*}UF",
            ".//{*}emit//{*}UF",
        ], default="")

        dt_emissao = find_text(root, [
            ".//{*}CompNfse//{*}Nfse//{*}InfNfse//{*}DataEmissao",
            ".//{*}Nfse//{*}InfNfse//{*}DataEmissao",
            ".//{*}InfNfse//{*}DataEmissao",
            ".//{*}infNFSe//{*}DPS//{*}infDPS//{*}dCompet",
            ".//{*}DPS//{*}infDPS//{*}dCompet",
            ".//{*}infDPS//{*}dCompet",
            ".//{*}infNFSe//{*}DPS//{*}infDPS//{*}dhEmi",
            ".//{*}DPS//{*}infDPS//{*}dhEmi",
            ".//{*}infDPS//{*}dhEmi",
        ], default="")

        dt_fmt = ""
        if dt_emissao:
            try:
                dt_raw = dt_emissao.split("T")[0]
                dt_fmt = datetime.strptime(dt_raw, "%Y-%m-%d").strftime("%d%m%Y")
            except (ValueError, IndexError):
                dt_fmt = ""

        chave_nfse = find_text(root, [
            ".//{*}CompNfse//{*}Nfse//{*}InfNfse//{*}CodigoVerificacao",
            ".//{*}Nfse//{*}InfNfse//{*}CodigoVerificacao",
            ".//{*}InfNfse//{*}CodigoVerificacao",
            ".//{*}infNFSe//{*}DPS//{*}infDPS//{*}id",
            ".//{*}DPS//{*}infDPS//{*}id",
            ".//{*}infDPS//{*}id",
        ], default="").replace("URN:prop:SefazNacional:nfse:id:", "").strip()

        # Chave NFS-e completa (50 dígitos do atributo Id de infNFSe).
        # Usada para construir o link de consulta no portal nacional.
        _inf_nfse = root.find(".//{*}infNFSe")
        chave_nfse_id = ""
        if _inf_nfse is not None:
            _id_attr = _inf_nfse.get("Id", "")
            if _id_attr.startswith("NFS"):
                chave_nfse_id = _id_attr[3:].strip()
            else:
                chave_nfse_id = _id_attr.strip()

        # Valor de deduções — usado pelo DMST-e e portais municipais.
        # Cai para "0.00" quando o XML não traz.
        valor_deducoes = find_text(root, [
            ".//{*}Servico//{*}Valores//{*}ValorDeducoes",
            ".//{*}ValoresNfse//{*}ValorDeducoes",
            ".//{*}ValorDeducoes",
            ".//{*}valores//{*}vDed",
            ".//{*}vDed",
        ], default="").strip() or "0.00"

        reg_ap_trib_sn = find_text(root, [
            ".//{*}infDPS//{*}regApTribSN",
            ".//{*}DPS//{*}infDPS//{*}regApTribSN",
            ".//{*}regApTribSN",
        ], default="")
        regime_esp_trib = find_text(root, [
            ".//{*}InfNfse//{*}RegimeEspecialTributacao",
            ".//{*}RegimeEspecialTributacao",
            ".//{*}Nfse//{*}InfNfse//{*}RegimeEspecialTributacao",
        ], default="")
        # Extrai opSimpNac aqui (e não mais abaixo) porque também precisamos
        # dele para identificar MEI no padrão Nacional (opSimpNac=2 = MEI).
        _op_simp_nac = find_text(root, [
            ".//{*}prest//{*}regTrib//{*}opSimpNac",
            ".//{*}regTrib//{*}opSimpNac",
            ".//{*}opSimpNac",
        ], default="").strip()
        eh_mei_raw = (
            reg_ap_trib_sn.strip() == "3"
            or regime_esp_trib.strip() == "5"
            or _op_simp_nac == "2"   # Nacional: opSimpNac=2 → MEI
        )
        # Veto: LTDA/S.A./EIRELI/etc não podem ser MEI (MEI é só Empresário Individual).
        # Alguns prestadores preenchem RegimeEspecialTributacao=5 errado para ME/EPP do
        # Simples Nacional; usamos a razão social como desempate robusto.
        _razao_upper = (razao_p or "").upper()
        _formas_nao_mei = (" LTDA", " S/A", " S.A.", " S A ", " S.A ", " SA ",
                            "EIRELI", " S/S", "EPP", " ME EPP")
        _eh_pessoa_juridica = any(f in f" {_razao_upper} " for f in _formas_nao_mei)
        eh_mei = eh_mei_raw and not _eh_pessoa_juridica

        # Local de prestação do serviço (código IBGE 7 dígitos) — campo novo do ISSNet.
        # Prioriza onde o serviço foi efetivamente prestado / incidência do ISS.
        local_prestacao = find_text(root, [
            ".//{*}Servico//{*}MunicipioIncidencia",
            ".//{*}MunicipioIncidencia",
            ".//{*}locPrest//{*}cLocPrestacao",
            ".//{*}cLocPrestacao",
            ".//{*}cLocIncid",
            ".//{*}Servico//{*}CodigoMunicipio",
        ], default="")
        local_prestacao = normalize_digits(local_prestacao)

        # Optante Simples Nacional / MEI — campo novo do ISSNet (1/2/3).
        # ABRASF: OptanteSimplesNacional (1=sim, 2=não)
        # Nacional: opSimpNac (1=Não, 2=MEI, 3=ME/EPP)
        # (_op_simp_nac já extraído acima junto com eh_mei)
        _optante_abrasf = find_text(root, [
            ".//{*}OptanteSimplesNacional",
        ], default="").strip()
        # Mapeia para o código do ISSNet:
        #   "3" → MEI
        #   "2" → Simples Nacional (não-MEI)
        #   "1" → Não Optante (explícito no XML)
        #   ""  → XML não trouxe info; enriquecimento posterior pode preencher.
        if eh_mei:
            optante_sn_mei = "3"
        elif _optante_abrasf == "1" or _op_simp_nac in ("2", "3"):
            # opSimpNac=2 só cai aqui se eh_mei foi vetado por LTDA — trata como SN comum
            optante_sn_mei = "2"
        elif _optante_abrasf == "2" or _op_simp_nac == "1":
            optante_sn_mei = "1"
        else:
            optante_sn_mei = ""

        dados = {
            "padrao": padrao,
            "numero": numero,
            "vlr_trib": vlr_trib,
            "vlr_doc": vlr_doc,
            "cnpj_p": cnpj_p,
            "razao_p": razao_p,
            "im_p": im_p,
            "iss_ret": iss_ret,
            "iss_ret_origem": iss_ret_origem,
            "uf": uf,
            "codigo_municipio": codigo_municipio,
            "aliq_val": aliq_val,
            "dt_fmt": dt_fmt,
            "item_lc_final": item_lc_final,
            "descricao_servico": descricao_servico,
            "x_desc_serv": x_desc_serv_raw,
            "discriminacao": discriminacao_raw,
            "c_trib_nac": ctribnac,
            "x_trib_nac": xtribnac,
            "x_trib_mun": xtribmun,
            "x_nbs": xnbs,
            "cep": cep,
            "endereco": endereco,
            "numero_end": numero_end,
            "bairro": bairro,
            "chave_nfse": chave_nfse,
            "chave_nfse_id": chave_nfse_id,
            "valor_deducoes": valor_deducoes,
            "numero_dps": numero_dps,
            "eh_mei": eh_mei,
            "local_prestacao": local_prestacao,
            "optante_sn_mei": optante_sn_mei,
        }

        if padrao == "desconhecido":
            return "desconhecido", dados

        # NAO ha fallback para local_prestacao: sao coisas diferentes.
        # local_prestacao = onde servico foi prestado; codigo_municipio = onde prestador esta.
        # Se prestador SC atende em Aparecida, cair em local_prestacao vaza modelo=2 errado.

        obrigatorios = ["numero", "vlr_doc", "cnpj_p", "dt_fmt", "codigo_municipio"]
        faltando = [c for c in obrigatorios if not has_value(dados.get(c))]
        if faltando:
            dados["_faltando"] = faltando
            return "incompleto", dados

        return "completo", dados

    except Exception as e:
        return "erro", {"_erro": str(e)}


def extrair_cabecalho_info(root):
    im_tomador = find_text(root, [
        ".//{*}TomadorServico//{*}IdentificacaoTomador//{*}InscricaoMunicipal",
        ".//{*}toma//{*}IM",
        ".//{*}toma//{*}InscricaoMunicipal",
        ".//{*}CNPJ/../IM",
    ], default="")

    razao_tomador = find_text(root, [
        ".//{*}TomadorServico//{*}RazaoSocial",
        ".//{*}toma//{*}xNome",
    ], default="")

    cnpj_tomador = find_text(root, [
        ".//{*}TomadorServico//{*}IdentificacaoTomador//{*}CpfCnpj//{*}Cnpj",
        ".//{*}TomadorServico//{*}IdentificacaoTomador//{*}Cnpj",
        ".//{*}toma//{*}CNPJ",
    ], default="")
    cnpj_tomador = normalize_digits(cnpj_tomador)

    mun_tomador = find_text(root, [
        ".//{*}DeclaracaoPrestacaoServico//{*}InfDeclaracaoPrestacaoServico//{*}TomadorServico//{*}Endereco//{*}CodigoMunicipio",
        ".//{*}TomadorServico//{*}Endereco//{*}CodigoMunicipio",
        ".//{*}infDPS//{*}toma//{*}end//{*}endNac//{*}cMun",
        ".//{*}DPS//{*}infDPS//{*}toma//{*}end//{*}endNac//{*}cMun",
        ".//{*}toma//{*}end//{*}endNac//{*}cMun",
    ], default="")

    data_emissao = find_text(root, [
        ".//{*}InfNfse//{*}DataEmissao",
        ".//{*}DataEmissao",
        ".//{*}dhProc",
        ".//{*}dhEmi",
    ], default="")

    return im_tomador, razao_tomador, data_emissao, mun_tomador, cnpj_tomador
