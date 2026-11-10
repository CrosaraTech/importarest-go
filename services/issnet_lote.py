"""
services/issnet_lote.py — execução desassistida do lote mensal de REST.

O BatchOrchestrator foi escrito para a UI: o gate de revisão manual publica na
fila e bloqueia numa threading.Event até a analista responder. Rodando de
madrugada não há quem responda, e a thread trava para sempre.

Este módulo drena a fila sem interface e responde ao gate imediatamente com
None (não preenche a nota). Só que devolver None faz o WorkflowProcessor
descartar a nota em silêncio e seguir — o TXT sairia incompleto, sem ninguém
perceber. Por isso cada pedido de revisão é registrado e, no fim, a empresa
inteira é reprovada: é a política "tudo ou nada por empresa", que evita entregar
declaração fiscal faltando nota.

Empresa reprovada não some — vai para a fila de revisão do dia seguinte.

Funções públicas:
    vigencia_anterior(hoje=None)     -> str   ("MMAAAA")
    executar_lote(...)               -> ResultadoLote
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from services.batch_orchestrator import BatchOrchestrator
from services.issnet_bucket import Empresa


# Status finais de uma empresa no lote.
OK       = "ok"        # TXT gerado, nenhuma nota pendente
REVISAO  = "revisao"   # alguma nota exigiu revisão manual -> reprovada
ERRO     = "erro"      # exceção durante o processamento
VAZIO    = "vazio"     # nenhuma nota na vigência (ou coleta desligada)


@dataclass
class EmpresaResultado:
    cod: str
    nome: str
    bucket: str
    status: str
    notas: int = 0
    segundos: float = 0.0
    detalhe: str = ""
    revisoes: list[str] = field(default_factory=list)   # chaves de NFS-e pendentes

    @property
    def apta_para_deposito(self) -> bool:
        """Só empresa 100% limpa é depositada automaticamente."""
        return self.status == OK and not self.revisoes


@dataclass
class ResultadoLote:
    vigencia: str
    destino: Path
    empresas: list[EmpresaResultado] = field(default_factory=list)
    segundos: float = 0.0

    @property
    def aptas(self) -> list[EmpresaResultado]:
        return [e for e in self.empresas if e.apta_para_deposito]

    @property
    def pendentes(self) -> list[EmpresaResultado]:
        return [e for e in self.empresas if not e.apta_para_deposito]

    def por_status(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for e in self.empresas:
            contagem[e.status] = contagem.get(e.status, 0) + 1
        return contagem


def vigencia_anterior(hoje: date | None = None) -> str:
    """Vigência a fechar no dia 3: sempre o mês anterior, no formato MMAAAA.

    Rodando em 03/05/2026 devolve "042026".
    """
    hoje = hoje or date.today()
    ano, mes = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
    return f"{mes:02d}{ano}"


def executar_lote(
    empresas: list[Empresa],
    vigencia: str,
    destino: Path,
    bucket_por_cod: dict[str, str],
    gerar_mei: bool = False,
    marcar_baixadas: bool = False,
    log_fn=None,
) -> ResultadoLote:
    """Processa as empresas e devolve o resultado de cada uma.

    `marcar_baixadas` fica desligado por padrão: marcar nota como baixada na
    Autmais antes de o TXT ser efetivamente importado no portal faria a nota
    sumir da próxima execução sem ter sido declarada.
    """
    destino.mkdir(parents=True, exist_ok=True)
    registrar = log_fn or (lambda _m: None)

    fila: queue.Queue = queue.Queue()
    orquestrador = BatchOrchestrator(fila)

    companies = [
        {"cod": e.cod, "razao": e.nome, "municipio": e.municipio}
        for e in empresas
    ]
    nomes = {e.cod: e.nome for e in empresas}

    worker = threading.Thread(
        target=orquestrador.run,
        args=(companies, vigencia, destino),
        kwargs={"gerar_mei": gerar_mei, "marcar_baixadas": marcar_baixadas,
                "analista": "LOTE_AUTOMATICO"},
        daemon=True,
    )
    worker.start()

    resultados: list[EmpresaResultado] = []
    revisoes: dict[str, list[str]] = {}
    total_segundos = 0.0

    while True:
        evento = fila.get()
        tipo = evento[0]

        if tipo == "manual_review":
            # (tipo, dados_base, chave_nfse, from_n8n, event, result_holder, cod, razao)
            _, _dados, chave, _from_n8n, event, holder, cod, _razao = evento
            revisoes.setdefault(cod, []).append(str(chave or "?"))
            holder[0] = None       # não preenche a nota
            event.set()            # libera a worker thread imediatamente
            registrar(f"[{cod}] nota {chave} exige revisão manual — empresa reprovada")

        elif tipo == "company_start":
            _, cod, i, total = evento
            registrar(f"[{cod}] {i + 1}/{total} — {nomes.get(cod, '')}")

        elif tipo == "company_done":
            _, cod, status, notas, segundos, detalhe = evento
            pendentes = revisoes.get(cod, [])
            if status in ("ok", "error") and pendentes:
                final = REVISAO
                detalhe = f"{len(pendentes)} nota(s) aguardando revisão manual"
            elif status == "ok" and notas == 0:
                final = VAZIO
                detalhe = "nenhuma nota na vigência (ou coleta desligada no Autmais)"
            elif status == "ok":
                final = OK
            elif status == "skipped":
                final = VAZIO
            else:
                final = ERRO
            resultados.append(EmpresaResultado(
                cod=cod, nome=nomes.get(cod, ""), bucket=bucket_por_cod.get(cod, "?"),
                status=final, notas=notas, segundos=segundos,
                detalhe=detalhe, revisoes=pendentes,
            ))

        elif tipo == "batch_done":
            total_segundos = evento[1].elapsed_total_seconds
            break

        # "log" e "counter" são ruído de UI — descartados de propósito.

    worker.join(timeout=30)
    return ResultadoLote(vigencia=vigencia, destino=destino,
                         empresas=resultados, segundos=total_segundos)

