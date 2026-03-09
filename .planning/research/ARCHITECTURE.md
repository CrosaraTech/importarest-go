# Architecture Research

**Domain:** Desktop batch processing integration — Python/Tkinter fiscal document app
**Researched:** 2026-03-09
**Confidence:** HIGH (baseado em leitura direta de processor.py e app.py)

---

## Ponto de Reuso: WorkflowProcessor

`WorkflowProcessor` já aceita todo o comportamento via 4 callbacks no construtor (`log_fn`, `progress_fn`, `contador_fn`, `abrir_tela_manual_fn`). O batch orchestrator constrói um `WorkflowProcessor` fresco por empresa com callbacks batch-aware. **Zero mudanças em `processor.py`.**

```python
# Fluxo individual atual (ui/app.py)
processor = WorkflowProcessor(
    log_fn=self.log,
    progress_fn=lambda total: self._set_progress_max(total),
    contador_fn=self._set_contador,
    abrir_tela_manual_fn=self._abrir_tela_manual_wrapper,
    gerar_mei=self._var_mei.get(),
)
result = processor.processar(emp_cod, vigencia)

# Batch orchestrator — mesmo padrão, callbacks diferentes
processor = WorkflowProcessor(
    log_fn=batch_log_fn,           # escreve no buffer de log do lote
    progress_fn=lambda total: ..., # atualiza progresso por nota (inner)
    contador_fn=batch_contador_fn, # atualiza contador de notas
    abrir_tela_manual_fn=skip_fn,  # no lote: auto-skip (retorna None)
    gerar_mei=False,               # lote sempre False
)
result = processor.processar(cod, vigencia)
```

---

## Revisão Manual no Lote — Auto-Skip

No lote, `abrir_tela_manual_fn` retorna `None` imediatamente. O `processor.py` já trata `None` como "Cancelado" (linhas 298-304 confirmadas) — a nota é logada e o processamento continua. Nenhum dialog de UI é aberto do background thread.

---

## Novos Arquivos (adições apenas)

```
services/
├── processor.py              # SEM MUDANÇAS
├── batch_orchestrator.py     # NOVO — loop do lote, tratamento de erros, salvamento de TXTs
└── spreadsheet.py            # NOVO — leitura XLSX via openpyxl

ui/
├── app.py                    # mudança mínima: adicionar tab Notebook
├── batch_panel.py            # NOVO — widgets e callbacks da UI do lote
└── dialogs.py                # SEM MUDANÇAS

config.py                     # adicionar PLANILHA_EMPRESAS + constantes de colunas
```

---

## Responsabilidades dos Componentes

| Componente | Responsabilidade | Localização |
|------------|-----------------|-------------|
| `JanelaCrosara` | UI do fluxo individual — sem mudanças | `ui/app.py` — existente |
| `PainelLote` | UI do lote: seleção, progresso, log, dialogs | `ui/batch_panel.py` — novo |
| `BatchOrchestrator` | Loop por empresa, tratamento de erros, salvamento | `services/batch_orchestrator.py` — novo |
| `SpreadsheetReader` | Lê XLSX, extrai colunas COD/ANALISTA | `services/spreadsheet.py` — novo |
| `WorkflowProcessor` | Pipeline por empresa — sem mudanças | `services/processor.py` — existente |

---

## Padrão de Threading — `after()` obrigatório

O `app.py` existente chama `janela.update()` do worker thread — funciona para operações curtas. Para o lote (minutos de execução), causa re-entrância. **Todo update de widget do batch deve usar `after()`:**

```python
# Thread-safe: agenda na main thread
def _log_thread_safe(self, msg: str):
    self.janela.after(0, self._append_log, msg)

def _append_log(self, msg: str):  # roda na main thread
    self.txt_log.configure(state="normal")
    self.txt_log.insert("end", msg + "\n")
    self.txt_log.see("end")
    self.txt_log.configure(state="disabled")
```

---

## Dialog de Erro — queue.Queue para handoff

Quando empresa falha, o background thread precisa bloquear até a analista decidir:

```python
# Background thread manda o erro para a queue
self._error_queue.put({"empresa": cod, "motivo": str(e)})
# Main thread (via after()) abre o dialog, coloca resultado na queue
# Background thread bloqueia:
action = self._response_queue.get(block=True)  # "skip" ou "abort"
```

---

## Integração com UI — Notebook Tab

Adicionar `ttk.Notebook` ao `JanelaCrosara` com duas abas: **"Individual"** (conteúdo existente) e **"Lote"** (novo `PainelLote`). Mudança mínima no `app.py` — nenhum widget existente é deletado.

O tamanho fixo da janela (420x580) precisará crescer para acomodar o log do lote.

---

## Fluxo de Dados

```
[PainelLote: analista, vigência, pasta destino]
    |
    | Thread spawn (daemon=True)
    v
[BatchOrchestrator.run()]
    |
    +-- SpreadsheetReader.load() → [(cod, analista)]
    |   filtrar por analista selecionada
    |
    +-- para cada empresa:
    |     WorkflowProcessor.processar(cod, vigencia)
    |       callbacks → after(0, ...) → widgets do PainelLote
    |     ProcessorResult → salvar TXT em pasta_destino/
    |     on_company_done → atualizar linha do log
    |
    +-- on_batch_complete → habilitar "Abrir pasta"
```

---

## Adições ao config.py

```python
PLANILHA_EMPRESAS = Path(
    r"G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx"
)
PLANILHA_COL_COD = 0      # Coluna A (índice 0)
PLANILHA_COL_ANALISTA = 3 # Coluna D (índice 3)
```

---

## Ordem de Implementação Sugerida

1. **`config.py`** — adicionar constantes da planilha
2. **`services/spreadsheet.py`** — leitor XLSX puro, sem UI, testável isolado
3. **`services/batch_orchestrator.py`** — lógica do lote com callbacks
4. **`ui/batch_panel.py`** — UI do lote com after() e queue
5. **`ui/app.py`** — refatorar para Notebook tab (por último, para não quebrar fluxo individual)

---

## Anti-Patterns a Evitar

| Evitar | Por quê | Fazer em vez |
|--------|---------|-------------|
| Chamar métodos privados de `processor.py` | Quebra encapsulamento | Usar só `processor.processar()` |
| `janela.update()` do worker no lote | Re-entrância em loops longos | `after(0, fn)` sempre |
| `messagebox` do background thread | Dialogs Tk devem ser na main thread | `queue.Queue` + `after()` |
| Flag `batch_mode` em `processor.py` | Mistura responsabilidades | Lógica batch fica no orchestrator |

---

*Architecture research: 2026-03-09*
