# Stack Research

**Domain:** Python/ttkbootstrap desktop app — batch XLSX processing + background job threading
**Researched:** 2026-03-09
**Confidence:** HIGH

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| openpyxl | 3.1.x | Leitura da planilha XLSX | Zero overhead para leitura de 2 colunas; sem cadeia de dependências NumPy/pandas; já mandatado em PROJECT.md |
| threading (stdlib) | Python 3.10+ | Rodar o lote em background | Já usado pelo app; evita freeze do Tkinter durante chamadas longas ao N8N |
| queue.Queue (stdlib) | Python 3.10+ | Passar eventos do worker thread para a UI | Único mecanismo thread-safe para comunicar com o main loop do Tkinter |
| after() (tkinter stdlib) | Python 3.10+ | Poll da queue no main loop | Alternativa Tkinter-safe a chamar métodos de widget do background thread |
| threading.Event (stdlib) | Python 3.10+ | Pause/abort do worker | Bloqueio zero-CPU quando empresa falha e UI precisa perguntar skip/abort |

### Nova Dependência

```bash
pip install openpyxl
```

Única nova dependência. Sem extensões C compiladas. Instalação rápida.

---

## Decisões Prescritas

### 1. openpyxl — não pandas

**Use openpyxl.**

Operação read-only em arquivo fixo conhecido: 2 colunas (A=COD, D=ANALISTA). Sem agregação, filtros, joins ou matemática.

```python
from openpyxl import load_workbook

wb = load_workbook(PLANILHA_PATH, read_only=True, data_only=True)
ws = wb.active
empresas = [
    (row[0].value, row[3].value)   # col A, col D (0-indexed)
    for row in ws.iter_rows(min_row=2)
    if row[0].value and row[3].value
]
wb.close()
```

pandas traria ~30 MB de extensões compiladas (NumPy, pytz) para zero benefício.

**Confiança:** HIGH — PROJECT.md já mandata openpyxl.

---

### 2. Padrão de threading — queue.Queue + after() polling

**Não estender o padrão existente (chamadas diretas ao widget do worker) para o lote.**

**Por que o padrão atual não escala para batch:**
- `ui/app.py` já chama `self.lbl_status.configure()` e `janela.update()` direto do background thread — funciona para operações curtas de empresa única
- Para o lote: worker chama log dezenas de vezes, por N empresas, com diálogos de erro mid-run → re-entrância do Tkinter → corrupção de estado

**Padrão correto:**

```python
# Worker envia mensagens tipadas via queue:
self._batch_queue.put({"type": "progress", "atual": i, "total": total, "empresa": cod, "eta_sec": eta})
self._batch_queue.put({"type": "log", "text": f"OK: {cod}", "level": "ok"})
self._batch_queue.put({"type": "empresa_erro", "empresa": cod, "motivo": str(e)})
self._batch_queue.put({"type": "done"})

# UI thread drena a queue via after():
def _poll_queue(self):
    try:
        while True:
            msg = self._batch_queue.get_nowait()
            self._handle_batch_msg(msg)
    except queue.Empty:
        pass
    if self._lote_ativo:
        self.janela.after(100, self._poll_queue)  # poll a cada 100ms
```

Toda atualização de widget acontece no `_handle_batch_msg()`, que roda na UI thread. Worker nunca toca widgets.

**Confiança:** HIGH — Prescrito no Python FAQ oficial para threading com Tkinter.

---

### 3. Pause/Abort — threading.Event

Quando empresa falha, o worker deve bloquear até a analista decidir:

```python
# Worker bloqueia aqui:
self._pause_event.clear()   # pausa o worker
self._pause_event.wait()    # zero-CPU até UI responder

# UI thread (no _handle_batch_msg ao receber "empresa_erro"):
resposta = messagebox.askquestion("Erro", f"{msg['empresa']} falhou. Pular?")
if resposta == "no":
    self._abort_flag = True
self._pause_event.set()  # desbloqueia o worker
```

`threading.Event` é bloqueio zero-CPU. `time.sleep()` polling desperdiça CPU e adiciona latência.

---

### 4. Barra de progresso e log

**Barra:** `ttk.Progressbar(mode="determinate", maximum=total)` — atualizar `value=atual` via mensagens da queue.

**ETA:**
```python
def _calc_eta(t_inicio, concluidos, total):
    if concluidos == 0:
        return 0.0
    avg = (time.time() - t_inicio) / concluidos
    return avg * (total - concluidos)
```

**Log por empresa:** `tk.Text` com `state="disabled"` + autoscroll. Não usar `ScrolledText` — não é estilizado pelo ttkbootstrap. Construir `tk.Text` + `ttk.Scrollbar` dentro de um `ttk.Frame`.

---

## O Que NÃO Usar

| Evitar | Por quê | Usar em vez |
|--------|---------|-------------|
| pandas | ~30 MB de dependências compiladas para 2 colunas | openpyxl |
| xlrd | Removeu suporte a XLSX na v2.0 (2020) | openpyxl |
| `janela.update()` no worker | Re-entrância do Tk em loop de lote | queue.Queue + after() |
| `messagebox` do background thread | Dialogs Tk devem ser criados na main thread | Enviar mensagem para queue; UI thread mostra o dialog |
| multiprocessing | Overhead de startup; N8N proíbe paralelismo | threading (um thread para todo o loop do lote) |

---

*Stack research: 2026-03-09*
