"""
services/issnet_bucket.py — classificação de empresas em buckets de importação ISSNet.

Cada arquivo TXT só pode ser importado no portal do município da empresa, logado
com o certificado digital que tem procuração para ela. A planilha de empresas já
traz MUNICIPIO e CERTIFICADO; este módulo lê essas colunas (que o
services/spreadsheet.py ignora) e agrupa as empresas em buckets.

Um bucket = (portal, certificado). Todas as empresas de um bucket são importadas
na mesma sessão, com um único login — que é o passo caro do processo.

Funções públicas:
    carregar_empresas()              -> list[Empresa]
    classificar(empresa)             -> Bucket
    bucketizar(empresas)             -> dict[str, list[Empresa]]
    resumo(buckets)                  -> str

Exceções:
    BucketError              (base)
    PlanilhaIndisponivel     (arquivo não encontrado ou bloqueado)
    PlanilhaFormatoInvalido  (cabeçalho ausente ou inesperado)
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from config import PLANILHA_EMPRESAS


# ---------------------------------------------------------------------------
# Exceções públicas
# ---------------------------------------------------------------------------

class BucketError(Exception):
    """Exceção base para falhas de bucketização."""


class PlanilhaIndisponivel(BucketError):
    """Planilha não encontrada, bloqueada ou inacessível."""


class PlanilhaFormatoInvalido(BucketError):
    """Planilha encontrada mas com cabeçalhos ausentes ou inesperados."""


# ---------------------------------------------------------------------------
# Portais ISSNet (Nota Control)
# ---------------------------------------------------------------------------

_BASE_ISSNET = "https://www.issnetonline.com.br"

PORTAIS = {
    "GOIANIA":              f"{_BASE_ISSNET}/goiania/Online/",
    "APARECIDA DE GOIANIA": f"{_BASE_ISSNET}/aparecida/online/",
    "ANAPOLIS":             f"{_BASE_ISSNET}/anapolis/online/",
    "TRINDADE":             f"{_BASE_ISSNET}/trindade/online/",
}

# Sigla curta por município, usada no nome da pasta do bucket.
_SIGLA_MUNICIPIO = {
    "GOIANIA": "GO",
    "APARECIDA DE GOIANIA": "APAR",
    "ANAPOLIS": "ANAP",
    "TRINDADE": "TRIN",
}

# Sigla curta por certificado. A planilha grava variações como
# "EDSON CROSARA (APARECIDA)" — o município já vem da coluna MUNICIPIO,
# então o sufixo entre parênteses é redundante e é descartado.
_SIGLA_CERTIFICADO = {
    "CROSARA CONTABILIDADE": "CROSARA",
    "EDSON CROSARA": "EDSON",
    "APARECIDA (OUTRO CERT)": "OUTRO",
}

# Valores da coluna CERTIFICADO que significam "ainda não descoberto".
_CERTIFICADO_VAZIO = {"", "NAO ENCONTRADA", "NAO ENCONTRADO"}

# Motivos pelos quais uma empresa fica fora do fluxo automático.
FORA_ESCOPO   = "FORA_ESCOPO"     # FECHAR REST/DMS != SIM
OUTRO_PORTAL  = "OUTRO_PORTAL"    # município não atendido pelo ISSNet
SEM_MUNICIPIO = "SEM_MUNICIPIO"   # coluna MUNICIPIO vazia
NAO_MAPEADA   = "NAO_MAPEADA"     # certificado desconhecido


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Empresa:
    cod: str
    nome: str
    cnpj: str
    analista: str
    municipio: str
    inscricao_municipal: str
    certificado: str
    fecha_rest: bool


@dataclass(frozen=True)
class Bucket:
    """Destino de importação de uma empresa.

    `apto` distingue os buckets que podem ser importados (portal e certificado
    conhecidos) dos que precisam de intervenção humana antes.
    """
    chave: str                 # "GO-CROSARA", "APAR-EDSON", "NAO_MAPEADA", ...
    portal: str | None         # URL do portal, None quando não aplicável
    certificado: str | None    # nome do certificado como está na planilha
    apto: bool
    motivo: str = ""           # preenchido só quando apto=False


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _sem_acento(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _norm(v) -> str:
    """Normaliza célula para comparação: sem acento, maiúscula, sem espaço extra."""
    if v is None:
        return ""
    return _sem_acento(str(v).strip().upper())


def _so_digitos(v) -> str:
    """CNPJ e IM chegam ora com máscara, ora sem — a planilha é inconsistente."""
    return "".join(c for c in str(v or "") if c.isdigit())


def _sigla_certificado(certificado: str) -> str | None:
    """Reduz o valor da planilha a uma sigla de bucket.

    O sufixo de município entre parênteses é ignorado: "EDSON CROSARA (ANAPOLIS)"
    e "EDSON CROSARA" são o mesmo certificado, e o município já vem de outra coluna.
    """
    if certificado in _SIGLA_CERTIFICADO:
        return _SIGLA_CERTIFICADO[certificado]
    base = certificado.split("(")[0].strip()
    return _SIGLA_CERTIFICADO.get(base)


# ---------------------------------------------------------------------------
# Leitura da planilha
# ---------------------------------------------------------------------------

_COLUNAS = {
    "cod": "COD",
    "nome": "NOME EMPRESA",
    "cnpj": "CNPJ",
    "analista": "ANALISTA",
    "municipio": "MUNICIPIO",
    "inscricao_municipal": "INSC. MUNICIPAL",
    "certificado": "CERTIFICADO",
    "fecha_rest": "FECHAR REST/DMS",
}


def carregar_empresas(caminho: Path | str | None = None) -> list[Empresa]:
    """Lê a planilha de empresas e devolve as linhas com COD preenchido.

    Diferente de services/spreadsheet.py, lê também MUNICIPIO, CERTIFICADO e
    FECHAR REST/DMS, e não filtra por município aceito — o filtro de escopo é
    responsabilidade de classificar().
    """
    caminho = Path(caminho or PLANILHA_EMPRESAS)
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except FileNotFoundError as exc:
        raise PlanilhaIndisponivel(f"Planilha não encontrada: {caminho}") from exc
    except (InvalidFileException, OSError, PermissionError) as exc:
        raise PlanilhaIndisponivel(
            f"Planilha inacessível (aberta em outro programa?): {caminho}"
        ) from exc

    try:
        ws = wb["Base"] if "Base" in wb.sheetnames else wb[wb.sheetnames[0]]
        linhas = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    if not linhas:
        raise PlanilhaFormatoInvalido(f"Planilha vazia: {caminho}")

    cabecalho = [_norm(c) for c in linhas[0]]
    indices: dict[str, int] = {}
    for campo, titulo in _COLUNAS.items():
        try:
            indices[campo] = cabecalho.index(_norm(titulo))
        except ValueError as exc:
            raise PlanilhaFormatoInvalido(
                f"Coluna '{titulo}' ausente. Cabeçalhos lidos: {cabecalho}"
            ) from exc

    def celula(linha, campo):
        i = indices[campo]
        return linha[i] if len(linha) > i else None

    empresas: list[Empresa] = []
    for linha in linhas[1:]:
        cod = str(celula(linha, "cod") or "").strip()
        if not cod:
            continue
        empresas.append(Empresa(
            cod=cod,
            nome=str(celula(linha, "nome") or "").strip(),
            cnpj=_so_digitos(celula(linha, "cnpj")),
            analista=_norm(celula(linha, "analista")),
            municipio=_norm(celula(linha, "municipio")),
            inscricao_municipal=_so_digitos(celula(linha, "inscricao_municipal")),
            certificado=_norm(celula(linha, "certificado")),
            fecha_rest=_norm(celula(linha, "fecha_rest")) == "SIM",
        ))
    return empresas


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------

def classificar(empresa: Empresa) -> Bucket:
    """Determina o bucket de importação de uma empresa.

    A ordem das checagens importa: escopo primeiro (empresa que não fecha REST
    não deveria nem ser processada), depois portal, depois certificado. Assim o
    motivo devolvido é sempre o primeiro obstáculo real, não um sintoma.
    """
    if not empresa.fecha_rest:
        return Bucket(FORA_ESCOPO, None, None, False,
                      "FECHAR REST/DMS não é SIM")

    if not empresa.municipio:
        return Bucket(SEM_MUNICIPIO, None, None, False,
                      "MUNICIPIO vazio na planilha")

    if empresa.municipio not in PORTAIS:
        return Bucket(OUTRO_PORTAL, None, None, False,
                      f"{empresa.municipio} não usa ISSNet")

    if empresa.certificado in _CERTIFICADO_VAZIO:
        return Bucket(NAO_MAPEADA, PORTAIS[empresa.municipio], None, False,
                      "CERTIFICADO não preenchido")

    sigla_cert = _sigla_certificado(empresa.certificado)
    if sigla_cert is None:
        return Bucket(NAO_MAPEADA, PORTAIS[empresa.municipio], None, False,
                      f"certificado desconhecido: {empresa.certificado}")

    sigla_mun = _SIGLA_MUNICIPIO[empresa.municipio]
    return Bucket(
        chave=f"{sigla_mun}-{sigla_cert}",
        portal=PORTAIS[empresa.municipio],
        certificado=empresa.certificado,
        apto=True,
    )


def bucketizar(empresas: list[Empresa]) -> dict[str, list[Empresa]]:
    """Agrupa empresas por chave de bucket.

    Ordena os buckets aptos primeiro (é a ordem em que a importação roda) e,
    dentro de cada um, por código — para que duas execuções da mesma vigência
    produzam a mesma sequência.
    """
    grupos: dict[str, list[Empresa]] = {}
    for empresa in empresas:
        grupos.setdefault(classificar(empresa).chave, []).append(empresa)

    def ordem_cod(e: Empresa):
        return (0, int(e.cod)) if e.cod.isdigit() else (1, 0, e.cod)

    inaptos = {FORA_ESCOPO, OUTRO_PORTAL, SEM_MUNICIPIO, NAO_MAPEADA}
    return {
        chave: sorted(grupos[chave], key=ordem_cod)
        for chave in sorted(grupos, key=lambda k: (k in inaptos, k))
    }


def resumo(buckets: dict[str, list[Empresa]]) -> str:
    """Resumo textual dos buckets, no formato que a skill do ISSNet apresenta."""
    linhas = []
    aptos = total_aptos = 0
    for chave, empresas in buckets.items():
        linhas.append(f"  {chave:16} {len(empresas):>4} empresas")
        if empresas and classificar(empresas[0]).apto:
            aptos += 1
            total_aptos += len(empresas)
    linhas.append(f"  {'':16} {'':>4}")
    linhas.append(f"  {aptos} buckets importáveis, {total_aptos} empresas")
    return "\n".join(linhas)
