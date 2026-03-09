# Features Research: Batch Processing UI

**Domain:** Desktop fiscal batch processing (NFS-e / Python / ttkbootstrap)
**Research Date:** 2026-03-09

---

## Table Stakes

Features the analyst expects to just work — missing any of these breaks the feature.

### Progress Feedback

- **Outer progress:** Company X/Y (barra de progresso geral)
- **Inner context:** Nome da empresa atual + competência sendo processada
- **Real-time log:** Lista rolável de resultados por empresa, atualizada em tempo real (sucesso/erro/pulado)
- **Estimativa de tempo:** Disponível após a primeira empresa ser concluída (baseado em média móvel)

### Error Handling UX

- **Error pause dialog (Skip / Abort):** Modal que bloqueia o lote quando uma empresa falha — a analista decide explicitamente
- **Post-run summary:** Totais (processadas, com sucesso, com erro, puladas) + lista de empresas que falharam
- **Manual review suppression:** Diálogos de revisão manual do fluxo individual DEVEM ser suprimidos no lote — notas que exigiriam revisão são tratadas como "Cancelado" e o lote continua

### Pre-Run Validation

- Validar os 3 inputs antes de habilitar Start: analista selecionada, competência válida, pasta de destino escolhida
- Botão Start desabilitado enquanto falta qualquer input
- Exibir contagem de empresas da analista selecionada antes de iniciar

### Controls

- **Botão Abort:** Disponível durante o processamento — cancela após a empresa atual terminar (não mata a meio)
- **Botão Start:** Desabilitado durante o processamento
- **Sem diálogos de Save durante o lote:** Pasta de destino escolhida antes do início — nenhuma interrupção mid-run

---

## Differentiators

Features que tornam a experiência significativamente melhor.

- **Contagem preview:** Após selecionar a analista, mostrar "X empresas encontradas" antes de iniciar
- **Auto-abrir pasta:** Abrir a pasta de destino no Explorer ao terminar o lote com sucesso
- **Relatório CSV consolidado do lote:** Além dos TXTs, gerar um CSV de auditoria do lote inteiro (empresa, resultado, notas processadas, erros)
- **Tempo restante estimado:** Estimativa exibida após a primeira empresa concluída

---

## Anti-Features

Coisas a deliberadamente NÃO construir.

| Anti-Feature | Motivo |
|---|---|
| Processamento paralelo de empresas | Proibido em PROJECT.md; custo N8N; dificulta tratamento de erro |
| Diálogos de revisão manual mid-batch | Destrói o valor da automação — a analista precisaria ficar presente |
| Diálogos de Save durante o lote | Interrompe o fluxo; pasta deve ser escolhida uma vez antes |
| Competência por empresa | Fora de escopo; adiciona complexidade sem necessidade imediata |
| Processamento em paralelo de notas | Pode sobrecarregar o N8N webhook |

---

## Error Handling Breakdown

| Cenário | Comportamento |
|---|---|
| Falha total da empresa (pasta não encontrada, zero notas) | Pause dialog → Skip ou Abort |
| Sucesso parcial (algumas notas falharam) | Conta como OK, log com contagem, sem pause |
| Revisão manual triggered | Suprimido por callback no-op; nota logada como Cancelado; lote continua |
| Erro de rede em uma nota | Capturado no nível da nota; sem pause |
| Planilha inacessível | Bloqueado na validação pré-run; Start permanece desabilitado com mensagem de erro |
| Timeout N8N | Capturado por try/except no n8n_client; empresa marcada como erro |

---

## Integration with Existing Flow

O fluxo individual existente (`processor.py`) já encapsula toda a lógica de processamento por empresa. O batch apenas:
1. Itera sobre a lista de empresas
2. Chama o mesmo `processor.py` para cada uma
3. Intercepta callbacks de progresso/resultado para atualizar a UI do lote
4. Suprime diálogos de revisão manual (callback no-op)

Não duplicar lógica de processamento — reutilizar `processor.py` integralmente.

---

*Features research completed: 2026-03-09*
