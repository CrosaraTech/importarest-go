# Pitfalls Research: Batch Processing

**Domain:** Python/ttkbootstrap desktop app — batch NFS-e processing via N8N
**Researched:** 2026-03-09
**Confidence:** HIGH (pitfalls identificados diretamente no código existente)

---

## Pitfall 1: Diálogos Tkinter criados pelo worker thread

**Severidade:** CRÍTICA — crashes intermitentes no Windows

**O que acontece:**
O `processor.py` já chama `_abrir_tela_manual()` do background thread (linhas 298, 355, 385, 420, 492), que abre `tk.Toplevel` e chama `wait_window()` — tudo fora da main thread. Para empresa única, funciona por coincidência. No lote, com dezenas de chamadas, causa crashes de segmentação no Windows.

**Sinais de alerta:**
- App congela ou fecha sem mensagem de erro durante o lote
- `RuntimeError: main thread is not in main loop`

**Prevenção:**
- Revisão manual **deve** ser suprimida no modo lote (callback no-op)
- Toda criação de widget (`Toplevel`, `messagebox`, `filedialog`) apenas da main thread via queue
- Fase de implementação: suprimir callbacks de revisão antes de integrar o lote

**Fase:** Implementação do batch controller

---

## Pitfall 2: `janela.update()` chamado do worker thread

**Severidade:** ALTA — re-entrância do Tkinter em loop de lote

**O que acontece:**
`ui/app.py` linha 148 chama `janela.update()` dentro do método `log()`, que é chamado do background thread. Para empresa única (fluxo existente), tolera-se. No lote, com chamadas repetidas em loop, o event loop do Tk é bombeado de fora da main thread — eventos de clique do usuário podem disparar mid-processing.

**Sinais de alerta:**
- Botões respondem enquanto o lote está rodando
- Estado inconsistente da UI após o lote terminar

**Prevenção:**
- Usar `queue.Queue` + `after()` polling — **nunca** chamar widgets do worker
- Remover `janela.update()` do caminho de execução do batch
- Ver STACK.md para o padrão completo

**Fase:** Implementação do batch controller

---

## Pitfall 3: Timeout do N8N multiplicado por todas as empresas

**Severidade:** ALTA — lote pode durar horas se o N8N estiver lento

**O que acontece:**
`n8n_client.py` usa `timeout=150` por chamada. Se o N8N demorar 150s por empresa e o lote tem 30 empresas → 75 minutos de timeout acumulado. A analista não sabe que o processo travou.

**Sinais de alerta:**
- ETA sobe ao invés de cair
- Uma empresa leva muito mais tempo que as outras

**Prevenção:**
- Considerar timeout mais conservador para o lote (ex: 60s) — o N8N deve responder rápido; 150s é excessivo
- Mostrar tempo da empresa atual na UI — analista percebe se uma empresa travou
- Tratar `requests.Timeout` como falha de empresa (pause dialog), não como crash

**Fase:** Implementação do batch controller

---

## Pitfall 4: Planilha bloqueada por outro usuário no drive G:

**Severidade:** ALTA — falha silenciosa ou crash na inicialização do lote

**O que acontece:**
A planilha fica em `G:\Drives compartilhados\...` — drive de rede compartilhado. Se outra analista estiver com o arquivo aberto no Excel, `openpyxl` recebe `PermissionError` ou lê o arquivo de lock temporário (`~$RELACAO_EMPRESAS.xlsx`) gerando `zipfile.BadZipFile`.

**Sinais de alerta:**
- Erro na pré-validação antes de mostrar a lista de analistas
- App trava na inicialização do lote sem mensagem clara

**Prevenção:**
- Abrir a planilha sempre com `read_only=True` (openpyxl) — reduz conflito
- Capturar `PermissionError`, `zipfile.BadZipFile`, e `FileNotFoundError` na leitura
- Exibir mensagem específica: "Não foi possível abrir a planilha. Verifique se ela está aberta em outro computador."
- Validar acesso na inicialização da aba de lote, não só ao clicar em Start

**Fase:** Integração da planilha

---

## Pitfall 5: Colunas da planilha acessadas por posição (quebra silenciosa)

**Severidade:** MÉDIA — dados errados processados sem erro aparente

**O que acontece:**
Se o arquivo for reorganizado (coluna inserida antes de A ou D), o código que acessa `row[0]` e `row[3]` vai ler colunas erradas silenciosamente. A empresa errada é processada, sem erro.

**Sinais de alerta:**
- Códigos de empresa inválidos aparecem no lote
- A lista de analistas mostra nomes estranhos

**Prevenção:**
- Acessar colunas por **header** (`ws["A"]` + verificar título), não por índice numérico
- Validar que o cabeçalho da linha 1 contém "COD" na coluna A e "ANALISTA" na coluna D
- Exibir mensagem de erro se a validação de cabeçalho falhar

**Fase:** Integração da planilha

---

## Pitfall 6: Dialog de pause/abort bloqueia indefinidamente (analista sai)

**Severidade:** MÉDIA — processo travado para sempre se analista sair da mesa

**O que acontece:**
Quando empresa falha, o worker bloqueia em `threading.Event.wait()` aguardando a decisão da analista. Se ela sair sem responder, o app fica travado indefinidamente com o worker parado.

**Sinais de alerta:**
- App está "rodando" mas sem progresso por horas

**Prevenção:**
- Adicionar timeout no dialog de erro: se não houver resposta em 5 minutos, escolher "pular" automaticamente
- Mostrar contador regressivo no dialog
- Ou: opção de "pular automaticamente em caso de erro" antes de iniciar o lote

**Fase:** Implementação do batch controller

---

## Pitfall 7: Cancelamento deixa saída parcial sem resumo

**Severidade:** MÉDIA — analista não sabe quais empresas foram processadas

**O que acontece:**
Se a analista clica em Abort mid-lote, os TXTs das empresas já processadas ficam na pasta destino, mas sem nenhum resumo. Na próxima execução, ela não sabe quais empresas já estão prontas.

**Sinais de alerta:**
- Pasta destino tem TXTs de algumas empresas, mas não todas

**Prevenção:**
- Ao abortar, sempre gerar o resumo final parcial (mesmo incompleto)
- O resumo deve listar: processadas com sucesso, com erro, puladas, e não iniciadas
- Exibir o resumo na UI ao abortar, não só ao completar

**Fase:** Implementação do batch controller

---

## Pitfall 8: Falha parcial de notas mascarada como sucesso da empresa

**Severidade:** MÉDIA — TXT gerado com dados faltando sem aviso

**O que acontece:**
Uma empresa pode ter 10 NFS-e, e 3 falharem no N8N. O `processor.py` atual pode continuar e gerar um TXT com as 7 notas restantes, sem indicar que 3 estão faltando. No lote, isso aparece como "OK" na empresa.

**Sinais de alerta:**
- TXT gerado tem menos notas do que o esperado
- Relatório CSV não bate com o número de NFS-e na pasta

**Prevenção:**
- Verificar `resultado.notas_com_erro` antes de marcar empresa como OK no log
- Se notas com erro > 0: marcar empresa como "OK com avisos" (warn) no log, não "OK"
- Incluir contagem de notas no log: "✓ EMPRESA001 — 10/10 notas | 3 c/ aviso"

**Fase:** Integração com processor.py existente

---

## Pitfall 9: Cache frio do IBGE trava as primeiras empresas do dia

**Severidade:** BAIXA — lentidão no início, não é falha

**O que acontece:**
`services/ibge.py` faz cache de respostas da API do IBGE. No primeiro lote do dia, todas as empresas com municípios não cacheados fazem chamadas HTTP — pode adicionar segundos por nota nas primeiras empresas.

**Sinais de alerta:**
- Primeiras empresas do lote demoram muito mais que as seguintes
- ETA sobe no início do lote

**Prevenção:**
- Não é necessário corrigir, apenas documentar no log de progresso
- Considerar pre-warm: carregar municípios comuns antes de iniciar o lote (opcional, v2)

**Fase:** Documentação / opcional

---

## Checklist "Parece Pronto, Mas Não Está"

Antes de declarar a feature completa:

- [ ] Testado com 3+ empresas em sequência (não só 1)
- [ ] Testado com erro na empresa do meio do lote
- [ ] Testado com abort no meio do lote
- [ ] Verificado que nenhum dialog de revisão manual aparece durante o lote
- [ ] Verificado que a UI não congela durante processamento
- [ ] Testado com planilha aberta por outro processo (simular lock)
- [ ] Resumo final correto após cancelamento parcial

---

## Tabela Resumo

| # | Pitfall | Severidade | Fase |
|---|---------|------------|------|
| 1 | Tkinter widgets do worker thread | CRÍTICA | Batch controller |
| 2 | `janela.update()` do worker | ALTA | Batch controller |
| 3 | N8N timeout multiplicado | ALTA | Batch controller |
| 4 | Planilha bloqueada no drive G: | ALTA | Integração planilha |
| 5 | Colunas acessadas por posição | MÉDIA | Integração planilha |
| 6 | Dialog de pause sem timeout | MÉDIA | Batch controller |
| 7 | Cancelamento sem resumo | MÉDIA | Batch controller |
| 8 | Falha parcial de notas mascarada | MÉDIA | Integração processor.py |
| 9 | Cache frio IBGE | BAIXA | Documentar |

---

*Pitfalls research: 2026-03-09*
