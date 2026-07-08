"""services/dmste_processor.py — Fluxo paralelo para DMST-e.

Lê XMLs de NFS-e de uma empresa para uma vigência e produz um CSV no layout
DMST-e (Declaração Mensal de Substituto Tributário Eletrônica).

Diferente do fluxo principal (TXT ISSNet), este NÃO chama n8n nem APIs
externas — usa apenas o extractor local e mapeia os campos diretamente.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from core.extractor import extrair_dados_python
from core.xml_parser import eh_evento_cancelamento, detectar_padrao_nfse
from core.dmste_builder import build_dmste_row, escrever_csv_dmste
from services.autmais_api import (
    baixar_xmls_da_empresa,
    vigencia_mmaaaa_para_yyyymm,
    get_cliente as get_cliente_autmais,
    AutmaisAPIError,
)


@dataclass
class DmsteResult:
    cod: str
    razao: str
    municipio: str
    status: str                    # "ok" | "pasta_inexistente" | "vazio" | "erro"
    notas_processadas: int = 0
    notas_canceladas: int = 0
    notas_erro: int = 0
    notas_fora_vigencia: int = 0
    notas_isentas: int = 0
    arquivo_saida: Path | None = None
    detalhe: str = ""
    linhas: list[dict] = field(default_factory=list)


def _carregar_xmls(pasta: Path) -> dict[str, str]:
    """Carrega XMLs e ZIPs da pasta — espelha o comportamento do WorkflowProcessor."""
    dict_xmls: dict[str, str] = {}
    for arq in pasta.glob("*"):
        if arq.suffix.lower() == ".xml":
            dict_xmls[arq.name] = arq.read_text(encoding="utf-8", errors="ignore")
        elif arq.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(arq, "r") as z:
                    for n in z.namelist():
                        if n.lower().endswith(".xml"):
                            dict_xmls[n] = z.read(n).decode("utf-8", errors="ignore")
            except (zipfile.BadZipFile, OSError):
                pass
    return dict_xmls


def _filtrar_eventos(dict_xmls: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    """Separa eventos de cancelamento dos XMLs de nota."""
    notas: dict[str, str] = {}
    canceladas: set[str] = set()
    for nome, conteudo in dict_xmls.items():
        if "_event_" in nome.lower():
            if eh_evento_cancelamento(conteudo):
                chave = nome.split("_event_")[0]
                canceladas.add(chave)
        else:
            notas[nome] = conteudo
    return notas, canceladas


def processar_empresa_dmste(
    cod: str,
    razao: str,
    municipio: str,
    vigencia: str,
    pasta_saida: Path,
    marcar_baixadas: bool = False,
) -> DmsteResult:
    """Processa todas notas de uma empresa para uma vigência e escreve o CSV.

    Args:
        cod: código da empresa.
        razao: razão social (usada no nome do arquivo).
        municipio: nome do município da empresa (vai na coluna MUNICIPIO).
        vigencia: formato 'mmaaaa' (ex: '052026').
        pasta_saida: diretório onde o CSV vai ser gravado.

    Returns:
        DmsteResult com contadores e caminho do arquivo gerado.
    """
    chaves_baixadas: list[str] = []
    try:
        yyyymm = vigencia_mmaaaa_para_yyyymm(vigencia)
        dict_xmls = baixar_xmls_da_empresa(
            cod, yyyymm,
            chaves_out=chaves_baixadas if marcar_baixadas else None,
        )
    except (AutmaisAPIError, ValueError) as e:
        return DmsteResult(
            cod=cod, razao=razao, municipio=municipio,
            status="erro", detalhe=f"Erro na API Autmais: {e}",
        )

    if not dict_xmls:
        return DmsteResult(
            cod=cod, razao=razao, municipio=municipio,
            status="vazio", detalhe="API nao retornou notas para essa vigencia.",
        )

    notas, canceladas = _filtrar_eventos(dict_xmls)
    linhas: list[dict] = []
    erros = 0
    fora_vigencia = 0
    isentas = 0

    for nome, conteudo in notas.items():
        chave_sem_ext = nome.replace(".xml", "").replace(".XML", "")
        if chave_sem_ext in canceladas:
            continue
        try:
            status, dados = extrair_dados_python(conteudo)
            if status in ("erro", "desconhecido"):
                erros += 1
                continue
            # Filtra notas fora da vigência selecionada (dt_fmt = ddmmaaaa,
            # vigência = mmaaaa). Portal DMST-e rejeita data divergente.
            dt = (dados.get("dt_fmt") or "").strip()
            if len(dt) == 8 and dt[2:] != vigencia:
                fora_vigencia += 1
                continue
            row = build_dmste_row(dados, municipio_empresa=municipio)
            # Pula notas com alíquota 0% (itens isentos como advocacia em
            # Crixás). O portal valida range 2-5% mesmo com ISS Retido = Não,
            # e essas notas não precisam ser declaradas no DMST-e.
            aliq_norm = (row.get("ALIQUOTA") or "").replace(",", ".").strip()
            if aliq_norm in ("0", "0.00", "0.0000", "0.000", ""):
                isentas += 1
                continue
            linhas.append(row)
        except (ET.ParseError, KeyError, ValueError):
            erros += 1
            continue

    safe_razao = "".join(
        c for c in (razao or "") if c not in '<>:"/\\|?*\r\n\t'
    ).strip().replace(" ", "_") or "EMPRESA"
    arquivo = pasta_saida / f"{cod}_{safe_razao}_{vigencia}.csv"

    if not linhas:
        return DmsteResult(
            cod=cod, razao=razao, municipio=municipio,
            status="vazio", notas_erro=erros,
            detalhe="Nenhuma nota válida extraída.",
        )

    escrever_csv_dmste(linhas, arquivo)

    # Marca notas como baixadas na API (opt-in, best-effort).
    if marcar_baixadas and chaves_baixadas:
        try:
            get_cliente_autmais().marcar_baixadas(chaves_baixadas)
        except AutmaisAPIError:
            pass  # silencioso — geracao ja foi sucesso

    return DmsteResult(
        cod=cod, razao=razao, municipio=municipio,
        status="ok",
        notas_processadas=len(linhas),
        notas_canceladas=len(canceladas),
        notas_erro=erros,
        notas_fora_vigencia=fora_vigencia,
        notas_isentas=isentas,
        arquivo_saida=arquivo,
        linhas=linhas,
    )
