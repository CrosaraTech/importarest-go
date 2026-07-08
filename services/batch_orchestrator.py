"""
services/batch_orchestrator.py — Phase 2 deliverable.

Provides thread-safe sequential company processing, queue-based progress
reporting, and the PROC-03 manual review pattern (queue.Queue + threading.Event).

Phase 3 (UI) imports and uses this module without any modifications here.
"""
import csv
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from services.processor import WorkflowProcessor
from core.txt_builder import montar_cabecalho
from core.txt_validator import detectar_campos_faltantes


@dataclass
class CompanyResult:
    cod: str
    status: str            # "ok" | "error" | "skipped"
    notes_count: int
    elapsed_seconds: float
    error_detail: str


@dataclass
class BatchSummary:
    total: int
    successes: int
    errors: int
    skipped: int
    aborted: bool
    company_results: list = field(default_factory=list)
    elapsed_total_seconds: float = 0.0


class BatchOrchestrator:

    def __init__(self, q: queue.Queue):
        self._queue = q
        self._abort_event = threading.Event()
        self._results: list[CompanyResult] = []
        self._faltantes_csv_path: Path | None = None

    def abort(self):
        """Called from main thread (UI abort button). Thread-safe."""
        self._abort_event.set()

    def run(self, companies: list[dict], vigencia: str,
            dest_folder: Path, gerar_mei: bool = False, analista: str = "",
            marcar_baixadas: bool = False):
        batch_start = time.monotonic()
        self._faltantes_csv_path = self._init_faltantes_csv(dest_folder, analista)
        total = len(companies)
        for i, company in enumerate(companies):
            if self._abort_event.is_set():
                break
            cod = company["cod"]
            razao = company.get("razao", "")
            # Municipio da empresa (da planilha) -> IBGE 7 pra decidir modelo TXT.
            from config import ibge_por_nome_municipio
            empresa_ibge = ibge_por_nome_municipio(company.get("municipio", ""))
            self._queue.put(("company_start", cod, i, total))
            self._process_one(cod, razao, vigencia, dest_folder, gerar_mei,
                              marcar_baixadas, empresa_ibge)
        elapsed = time.monotonic() - batch_start
        summary = self._build_summary(total, self._abort_event.is_set(), elapsed)
        self._queue.put(("batch_done", summary))

    def _init_faltantes_csv(self, dest_folder: Path, analista: str) -> Optional[Path]:
        """Cria CSV de campos faltantes do batch — sobrescreve sempre.

        Cada execução começa com CSV zerado, só com o cabeçalho. As linhas
        com faltantes são anexadas ao longo do processamento via
        `_registrar_faltantes`. Resultado: o CSV reflete apenas a execução
        atual, sem mistura com runs anteriores.
        """
        safe = "".join(
            c for c in (analista or "") if c not in '<>:"/\\|?*\r\n\t'
        ).strip()
        if not safe:
            return None
        path = dest_folder / f"Faltantes_{safe}.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([
                "Empresa Codigo", "Empresa Razao", "Vigencia",
                "Numero da Nota", "CNPJ Prestador", "Razao Prestador",
                "Valor Documento", "Data Emissao",
                "Campos Faltantes", "Linha Completa",
            ])
        return path

    def _registrar_faltantes(self, cod: str, razao_emp: str, vigencia: str, result):
        """Anexa ao CSV linhas geradas que possuem ao menos um campo obrigatorio vazio."""
        if not self._faltantes_csv_path or not result:
            return
        rows: list[list[str]] = []

        def _coletar(linha: str, vig: str):
            faltantes = detectar_campos_faltantes(linha)
            if not faltantes:
                return
            partes = linha.split(";")
            rows.append([
                cod, razao_emp, vig,
                partes[1] if len(partes) > 1 else "",
                partes[7] if len(partes) > 7 else "",
                partes[8] if len(partes) > 8 else "",
                partes[3] if len(partes) > 3 else "",
                partes[5] if len(partes) > 5 else "",
                ", ".join(faltantes),
                linha,
            ])

        for linha in result.linhas_dict.values():
            _coletar(linha, vigencia)
        for vig_err, linhas_err in result.notas_vig_errada.items():
            for linha in linhas_err:
                _coletar(linha, vig_err)

        if rows:
            with open(self._faltantes_csv_path, "a", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                for row in rows:
                    w.writerow(row)

    def _process_one(self, cod, razao, vigencia, dest_folder, gerar_mei,
                     marcar_baixadas=False, empresa_ibge=""):
        t0 = time.monotonic()
        try:
            processor = WorkflowProcessor(
                log_fn=lambda msg: self._queue.put(("log", cod, msg)),
                progress_fn=lambda total: self._queue.put(("counter", cod, 0, total)),
                contador_fn=lambda a, t: self._queue.put(("counter", cod, a, t)),
                abrir_tela_manual_fn=self._make_manual_callback(cod, razao),
                gerar_mei=gerar_mei,
                marcar_baixadas=marcar_baixadas,
            )
            result = processor.processar(cod, vigencia, empresa_ibge=empresa_ibge)
            if result is None:
                elapsed = time.monotonic() - t0
                self._record(cod, "skipped", 0, elapsed, "Pasta não encontrada")
                self._queue.put(("company_done", cod, "skipped", 0, elapsed, "Pasta não encontrada"))
                return
            self._save_txt(result, cod, razao, vigencia, dest_folder)
            self._registrar_faltantes(cod, razao, vigencia, result)
            # Pos-sucesso: marca notas baixadas na Autmais (opt-in, best-effort).
            if marcar_baixadas:
                marcadas = processor.marcar_baixadas_na_autmais()
                if marcadas:
                    self._queue.put(("log", cod, f"✅ {marcadas} nota(s) marcada(s) como baixada(s) na Autmais."))
            notes = len(result.linhas_dict)
            elapsed = time.monotonic() - t0
            self._record(cod, "ok", notes, elapsed, "")
            self._queue.put(("company_done", cod, "ok", notes, elapsed, ""))
        except Exception as exc:
            elapsed = time.monotonic() - t0
            self._record(cod, "error", 0, elapsed, str(exc))
            self._queue.put(("company_done", cod, "error", 0, elapsed, str(exc)))

    def _make_manual_callback(self, cod: str, razao: str = ""):
        def callback(dados_base: dict, chave_nfse: str,
                     from_n8n: bool = False) -> Optional[str]:
            event = threading.Event()
            result_holder = [None]
            self._queue.put(("manual_review", dados_base, chave_nfse,
                             from_n8n, event, result_holder, cod, razao))
            event.wait()          # blocks worker; releases GIL
            return result_holder[0]
        return callback

    def _save_txt(self, result, cod: str, razao: str, vigencia: str, dest: Path):
        safe_razao = "".join(
            c for c in (razao or "") if c not in '<>:"/\\|?*\r\n\t'
        ).strip().replace(" ", "_")
        cnpj_part = (result.cnpj_tomador_cab or "").strip()
        # Formato: {cod}_{cnpj}_{razao}_{vigencia}.txt
        partes = [cod]
        if cnpj_part:
            partes.append(cnpj_part)
        if safe_razao:
            partes.append(safe_razao)
        partes.append(vigencia)
        nome_base = "_".join(partes)
        if result.conteudo_final:
            (dest / f"{nome_base}.txt").write_text(
                result.conteudo_final, encoding="utf-8"
            )
        for vig_err, linhas in result.notas_vig_errada.items():
            dt_iso = f"{vig_err[2:]}-{vig_err[:2]}-01T00:00:00"
            cab = montar_cabecalho(result.im_tomador_cab,
                                   result.razao_tomador_cab, dt_iso)
            content = "\n".join(([cab] if cab else []) + linhas)
            partes_err = [cod]
            if cnpj_part:
                partes_err.append(cnpj_part)
            if safe_razao:
                partes_err.append(safe_razao)
            partes_err.append(vig_err)
            (dest / f"{'_'.join(partes_err)}.txt").write_text(content, encoding="utf-8")

    def _record(self, cod, status, notes, elapsed, detail):
        self._results.append(
            CompanyResult(cod=cod, status=status, notes_count=notes,
                          elapsed_seconds=elapsed, error_detail=detail)
        )

    def _build_summary(self, total: int, aborted: bool,
                       elapsed: float) -> BatchSummary:
        return BatchSummary(
            total=total,
            successes=sum(1 for r in self._results if r.status == "ok"),
            errors=sum(1 for r in self._results if r.status == "error"),
            skipped=sum(1 for r in self._results if r.status == "skipped"),
            aborted=aborted,
            company_results=list(self._results),
            elapsed_total_seconds=elapsed,
        )
