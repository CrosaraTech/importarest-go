"""Cliente HTTP da API Autmais (NFS-e).

Responsabilidades:
- Autenticar via signin30days e cachear o token JWT em disco.
- Listar notas de servico de um CNPJ tomador para uma vigencia (YYYY-MM).
- Baixar o XML cru de uma nota a partir da url_xml.

A API tem 3 hosts:
- api2.autmais.com.br/v1     -> autenticacao
- api3.autmais.com.br/v1     -> /companie/index_contabil
- apimongo.autmais.com.br/v1 -> /notas_servico (descoberto via test)
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import requests

from config import (
    AUTMAIS_AUTH_HOST,
    AUTMAIS_NFSE_HOST,
    AUTMAIS_TENANT,
    AUTMAIS_USERNAME,
    AUTMAIS_PASSWORD,
    AUTMAIS_TOKEN_CACHE,
)

# Endpoint de empresas (descoberto no teste — fica em api3, nao em apimongo).
AUTMAIS_EMPRESAS_HOST = "https://api3.autmais.com.br/v1"


class AutmaisAPIError(Exception):
    pass


class AutmaisClient:
    """Cliente reutilizavel. Cacheia token em memoria e disco.

    Uso:
        cli = AutmaisClient()
        for nota in cli.listar_notas(cnpj_tomador="01834860000193", ano_mes="2026-05"):
            xml_str = cli.baixar_xml(nota["url_xml"])
            ...
    """

    DEFAULT_PAGE_SIZE = 100
    REQUEST_TIMEOUT = 60

    def __init__(self):
        self._token: str | None = None
        self._token_exp: datetime | None = None
        self._sess = requests.Session()
        self._sess.headers.update({"tenant": AUTMAIS_TENANT})
        # Cache cod -> cnpj para evitar listar empresas a cada chamada.
        self._cache_empresas: dict[str, dict] | None = None

    # ------------------------------------------------------------------
    # Autenticacao
    # ------------------------------------------------------------------
    def _carregar_token_cache(self) -> bool:
        try:
            data = json.loads(AUTMAIS_TOKEN_CACHE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False
        exp_str = data.get("exp")
        token = data.get("token")
        if not exp_str or not token:
            return False
        try:
            exp = datetime.fromisoformat(exp_str)
        except ValueError:
            return False
        if exp <= datetime.now() + timedelta(hours=2):
            return False  # vence em < 2h, melhor renovar
        self._token = token
        self._token_exp = exp
        return True

    def _salvar_token_cache(self):
        if not self._token or not self._token_exp:
            return
        try:
            AUTMAIS_TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
            AUTMAIS_TOKEN_CACHE.write_text(
                json.dumps({
                    "token": self._token,
                    "exp": self._token_exp.isoformat(),
                }),
                encoding="utf-8",
            )
        except OSError:
            pass  # cache best-effort

    def _autenticar(self):
        url = f"{AUTMAIS_AUTH_HOST}/auth/signin30days"
        body = {"username": AUTMAIS_USERNAME, "password": AUTMAIS_PASSWORD}
        try:
            r = self._sess.post(url, json=body, timeout=self.REQUEST_TIMEOUT)
        except requests.RequestException as e:
            raise AutmaisAPIError(f"Falha de conexao no login: {e}") from e
        if r.status_code not in (200, 201):
            raise AutmaisAPIError(
                f"Login falhou ({r.status_code}): {r.text[:300]}"
            )
        data = r.json()
        token = data.get("accessToken") or data.get("access_token") or data.get("token")
        if not token:
            raise AutmaisAPIError(f"Resposta de login sem accessToken: {r.text[:300]}")
        self._token = token
        # signin30days = 30 dias de validade
        self._token_exp = datetime.now() + timedelta(days=29)
        self._salvar_token_cache()

    def _garantir_token(self):
        if self._token and self._token_exp and self._token_exp > datetime.now() + timedelta(hours=2):
            return
        if self._carregar_token_cache():
            return
        self._autenticar()

    def _auth_headers(self) -> dict:
        self._garantir_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------------
    # Notas de servico
    # ------------------------------------------------------------------
    @staticmethod
    def _datas_vigencia(ano_mes: str) -> tuple[str, str]:
        """'2026-05' -> ('2026-05-01', '2026-05-31')."""
        ano_s, mes_s = ano_mes.split("-")
        ano, mes = int(ano_s), int(mes_s)
        start = f"{ano:04d}-{mes:02d}-01"
        if mes == 12:
            prox = datetime(ano + 1, 1, 1)
        else:
            prox = datetime(ano, mes + 1, 1)
        end = (prox - timedelta(days=1)).strftime("%Y-%m-%d")
        return start, end

    def _paginar(
        self,
        cnpj_tomador: str,
        date_filter: dict,
        *,
        page_size: int,
        max_paginas: int,
    ) -> Iterator[dict]:
        """Pagina /notas_servico com um conjunto de filtros de data.

        date_filter ex: {'startDateEmissao': '2026-05-01', 'endDateEmissao': '2026-05-31'}
        ou           : {'startDateUpdate':  '2026-05-01', 'endDateUpdate':  '2026-05-31'}
        """
        url = f"{AUTMAIS_NFSE_HOST}/notas_servico"

        for page in range(1, max_paginas + 1):
            params = {
                "inscricaoFederalDestinatario": cnpj_tomador,
                "_page": page,
                "_limit": page_size,
                **date_filter,
            }
            headers = self._auth_headers()
            try:
                r = self._sess.get(url, params=params, headers=headers, timeout=self.REQUEST_TIMEOUT)
            except requests.RequestException as e:
                raise AutmaisAPIError(f"Falha de conexao ao listar notas: {e}") from e

            if r.status_code == 401:
                self._autenticar()
                headers = self._auth_headers()
                r = self._sess.get(url, params=params, headers=headers, timeout=self.REQUEST_TIMEOUT)

            if r.status_code != 200:
                raise AutmaisAPIError(
                    f"GET /notas_servico falhou ({r.status_code}): {r.text[:300]}"
                )

            data = r.json()
            if isinstance(data, dict):
                for k in ("data", "items", "results", "notas"):
                    if isinstance(data.get(k), list):
                        data = data[k]
                        break
            if not isinstance(data, list):
                raise AutmaisAPIError(f"Resposta inesperada: tipo={type(data).__name__}")

            if not data:
                return

            for nota in data:
                yield nota

            if len(data) < page_size:
                return  # ultima pagina

    def listar_notas(
        self,
        cnpj_tomador: str,
        ano_mes: str,
        *,
        page_size: int | None = None,
        max_paginas: int = 50,
    ) -> Iterator[dict]:
        """Itera notas de um CNPJ tomador na vigencia (UNION de 2 filtros).

        Estrategia:
        1. Busca por `startDateEmissao` na vigencia (caso normal).
        2. Busca por `startDateUpdate` na vigencia (cobre notas emitidas
           em outro mes mas cadastradas/sincronizadas na Autmais agora).
        3. Dedup por `_id` / `chave_nota`.

        O filtro de vigencia DEFINITIVO acontece em processor.py via
        `_filtrar_vigencia` (compara dt_emissao do XML com a vigencia
        escolhida). Notas fora da vigencia vao para `notas_vig_errada` —
        reportadas mas nao gravadas no TXT/CSV.
        """
        start, end = self._datas_vigencia(ano_mes)
        limit = page_size or self.DEFAULT_PAGE_SIZE
        chaves_vistas: set[str] = set()

        # Busca 1 — por emissao (caso comum)
        for nota in self._paginar(
            cnpj_tomador,
            {"startDateEmissao": start, "endDateEmissao": end},
            page_size=limit, max_paginas=max_paginas,
        ):
            chave = nota.get("_id") or nota.get("chave_nota")
            if chave and chave in chaves_vistas:
                continue
            if chave:
                chaves_vistas.add(chave)
            yield nota

        # Busca 2 — por update (pega lancamentos atrasados na Autmais)
        for nota in self._paginar(
            cnpj_tomador,
            {"startDateUpdate": start, "endDateUpdate": end},
            page_size=limit, max_paginas=max_paginas,
        ):
            chave = nota.get("_id") or nota.get("chave_nota")
            if chave and chave in chaves_vistas:
                continue
            if chave:
                chaves_vistas.add(chave)
            yield nota

    # ------------------------------------------------------------------
    # Empresas (cadastro contabil)
    # ------------------------------------------------------------------
    def listar_empresas(self, *, force_refresh: bool = False) -> dict[str, dict]:
        """Retorna dict {codigo_contabil: {cnpj, razao, ibge, municipio, ...}}.

        codigo_contabil = codeCompanieAccountSystem (string).
        Resultado e cacheado em memoria; passe force_refresh=True para revalidar.
        """
        if self._cache_empresas is not None and not force_refresh:
            return self._cache_empresas

        url = f"{AUTMAIS_EMPRESAS_HOST}/companie/index_contabil"
        empresas: dict[str, dict] = {}
        for page in range(1, 100):
            params = {"status": "ACTIVE", "_page": page, "_limit": 100}
            headers = self._auth_headers()
            try:
                r = self._sess.get(url, params=params, headers=headers, timeout=self.REQUEST_TIMEOUT)
            except requests.RequestException as e:
                raise AutmaisAPIError(f"Falha de conexao ao listar empresas: {e}") from e
            if r.status_code == 401:
                self._autenticar()
                headers = self._auth_headers()
                r = self._sess.get(url, params=params, headers=headers, timeout=self.REQUEST_TIMEOUT)
            if r.status_code != 200:
                raise AutmaisAPIError(
                    f"GET /companie/index_contabil falhou ({r.status_code}): {r.text[:300]}"
                )
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            for emp in data:
                cod = str(emp.get("codeCompanieAccountSystem") or "").strip()
                cnpj = str(emp.get("federalRegistration") or "").strip()
                if not cod or not cnpj:
                    continue
                empresas[cod] = {
                    "cnpj": cnpj,
                    "razao": str(emp.get("name") or "").strip(),
                    "ibge": str(emp.get("idIbgeCity") or "").strip(),
                    "municipio": str(emp.get("nameCity") or "").strip(),
                    "uf": str(emp.get("stateCity") or "").strip(),
                    "im": str(emp.get("cityRegistrationData") or emp.get("cityRegistration") or "").strip(),
                    "ie": str(emp.get("stateRegistrationData") or emp.get("stateRegistration") or "").strip(),
                    "id_companie": str(emp.get("idCompanie") or "").strip(),
                }
            if len(data) < 100:
                break

        self._cache_empresas = empresas
        return empresas

    def buscar_cnpj_por_cod(self, cod: str) -> str | None:
        """Mapeia codigo contabil -> CNPJ tomador. None se nao achou."""
        cod = str(cod).strip()
        empresas = self.listar_empresas()
        emp = empresas.get(cod)
        return emp["cnpj"] if emp else None

    # ------------------------------------------------------------------
    # XML cru
    # ------------------------------------------------------------------
    def baixar_xml(self, url_xml: str) -> str:
        """Baixa o XML cru de uma nota a partir da url_xml.

        A url e de CDN publica (files-autmais-generic.autmais.com),
        nao precisa de auth.
        """
        try:
            r = requests.get(url_xml, timeout=self.REQUEST_TIMEOUT)
        except requests.RequestException as e:
            raise AutmaisAPIError(f"Falha ao baixar XML: {e}") from e
        if r.status_code != 200:
            raise AutmaisAPIError(f"Download XML falhou ({r.status_code}) em {url_xml}")
        return r.text

    # ------------------------------------------------------------------
    # Marcacao de status (opt-in: usuario pode desligar via toggle)
    # ------------------------------------------------------------------
    def marcar_baixadas(self, chaves: list[str]) -> dict:
        """PUT /notas_servico/status_download — marca lista de chaves como baixadas.

        Body confirmado por teste: {"chave_nota": ["id1","id2",...]}.
        Retorna o objeto Mongo-style com matchedCount/modifiedCount.
        """
        if not chaves:
            return {"matchedCount": 0, "modifiedCount": 0}
        url = f"{AUTMAIS_NFSE_HOST}/notas_servico/status_download"
        headers = self._auth_headers()
        try:
            r = self._sess.put(url, json={"chave_nota": chaves}, headers=headers, timeout=self.REQUEST_TIMEOUT)
        except requests.RequestException as e:
            raise AutmaisAPIError(f"Falha de conexao em PUT status_download: {e}") from e
        if r.status_code == 401:
            self._autenticar()
            headers = self._auth_headers()
            r = self._sess.put(url, json={"chave_nota": chaves}, headers=headers, timeout=self.REQUEST_TIMEOUT)
        if r.status_code not in (200, 201, 204):
            raise AutmaisAPIError(
                f"PUT status_download falhou ({r.status_code}): {r.text[:300]}"
            )
        try:
            return r.json()
        except ValueError:
            return {}


# Singleton conveniente — UI e processor compartilham o mesmo token cacheado.
_cliente_singleton: AutmaisClient | None = None


def get_cliente() -> AutmaisClient:
    global _cliente_singleton
    if _cliente_singleton is None:
        _cliente_singleton = AutmaisClient()
    return _cliente_singleton


def baixar_xmls_da_empresa(
    cod: str,
    vigencia_yyyymm: str,
    *,
    log_fn=None,
    max_workers: int = 8,
    chaves_out: list[str] | None = None,
) -> dict[str, str]:
    """High-level: dado cod contabil + vigencia (YYYY-MM), retorna {nome_arq: xml_string}.

    Funcao compartilhada por processor.py (TXT ISSNet) e
    dmste_processor.py (CSV DMST-e) para evitar duplicacao.

    Args:
        cod: codigo contabil da empresa (planilha col COD).
        vigencia_yyyymm: '2026-05'.
        log_fn: callback opcional para mensagens (str).
        chaves_out: lista opcional que sera preenchida com as chaves
            (`_id`) das notas baixadas — usado para chamar
            `marcar_baixadas()` depois de gerar com sucesso.

    Returns:
        dict {nome_arquivo: conteudo_xml}. Vazio se nada encontrado.
    """
    def _log(msg: str):
        if log_fn:
            log_fn(msg)

    cli = get_cliente()
    cnpj = cli.buscar_cnpj_por_cod(cod)
    if not cnpj:
        _log(f"❌ Empresa cod={cod} nao encontrada no cadastro Autmais.")
        return {}

    _log(f"🔎 API Autmais — CNPJ={cnpj} vigencia={vigencia_yyyymm}")
    notas = list(cli.listar_notas(cnpj, vigencia_yyyymm))
    if not notas:
        _log(f"📭 0 notas para CNPJ={cnpj} em {vigencia_yyyymm}.")
        return {}

    _log(f"📥 {len(notas)} nota(s). Baixando XMLs em paralelo...")
    dict_xmls: dict[str, str] = {}

    def _baixar(nota: dict):
        url = nota.get("url_xml")
        if not url:
            return None
        chave = nota.get("_id") or nota.get("chave_nota") or str(nota.get("numero_nf", ""))
        nome_arq = f"{chave}.xml"
        try:
            conteudo = cli.baixar_xml(url)
        except AutmaisAPIError:
            return None
        return nome_arq, conteudo, chave

    chaves_baixadas: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_baixar, n) for n in notas]
        for fut in as_completed(futs):
            res = fut.result()
            if res:
                nome, conteudo, chave = res
                dict_xmls[nome] = conteudo
                chaves_baixadas.append(chave)

    faltam = len(notas) - len(dict_xmls)
    if faltam:
        _log(f"⚠️ {faltam} XML(s) falharam no download — ignorados.")

    if chaves_out is not None:
        chaves_out.extend(chaves_baixadas)

    return dict_xmls


def vigencia_mmaaaa_para_yyyymm(vig: str) -> str:
    """Converte '052026' -> '2026-05'. Aceita ja-yyyy-mm tambem."""
    vig = str(vig).strip()
    if "-" in vig and len(vig) == 7:
        return vig  # ja esta no formato
    if len(vig) == 6 and vig.isdigit():
        mes, ano = vig[:2], vig[2:]
        return f"{ano}-{mes}"
    raise ValueError(f"Vigencia invalida (esperado mmaaaa ou yyyy-mm): {vig!r}")
