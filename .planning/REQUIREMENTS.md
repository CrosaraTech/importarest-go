# Requirements: ImportaREST GO — Processamento em Lote

**Defined:** 2026-03-09
**Core Value:** Analistas geram arquivos REST de NFS-e com o mínimo de intervenção manual — individualmente ou em lote por competência.

---

## v1 Requirements

### Planilha

- [x] **PLAN-01**: Sistema lê automaticamente a planilha do caminho fixo `G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx` ao abrir a aba de lote
- [x] **PLAN-02**: Sistema filtra e exibe apenas as empresas onde a coluna MUNICIPIO contém "GOIÂNIA"
- [x] **PLAN-03**: Sistema valida que as colunas COD (coluna A) e ANALISTA (coluna D) existem no cabeçalho antes de prosseguir
- [x] **PLAN-04**: Sistema exibe mensagem de erro clara se a planilha estiver inacessível (bloqueada, não encontrada, ou formato inválido)
- [x] **PLAN-05**: Após seleção da analista, sistema exibe a contagem de empresas encontradas para ela

### Seleção e Entrada

- [ ] **SELEC-01**: Analista pode selecionar seu nome a partir de uma lista de analistas extraída da planilha (somente analistas com empresas em GOIÂNIA)
- [ ] **SELEC-02**: Analista pode inserir a competência (mês/ano) que será aplicada a todas as empresas do lote
- [ ] **SELEC-03**: Analista pode selecionar a pasta de destino onde todos os TXTs do lote serão salvos
- [ ] **SELEC-04**: Botão de início fica desabilitado até que analista, competência e pasta de destino estejam todos preenchidos

### Processamento

- [ ] **PROC-01**: Sistema processa todas as empresas da analista (GOIÂNIA) em sequência, sem intervenção manual entre elas
- [ ] **PROC-02**: Quando uma empresa falha, o sistema registra o erro no log e pula automaticamente para a próxima empresa
- [ ] **PROC-03**: Quando uma nota exige revisão manual durante o lote, o sistema pausa e exibe o diálogo de revisão normalmente — após a analista responder, o lote continua
- [ ] **PROC-04**: Analista pode clicar em "Abortar" a qualquer momento — sistema para após a empresa atual terminar

### Progresso

- [ ] **PROG-01**: UI exibe barra de progresso com contagem X/Y empresas durante o lote
- [ ] **PROG-02**: UI exibe o código/nome da empresa sendo processada no momento
- [ ] **PROG-03**: UI exibe estimativa de tempo restante após a primeira empresa concluir
- [ ] **PROG-04**: UI exibe log rolável com resultado por empresa (sucesso / erro / pulada)

### Resultado

- [ ] **RESULT-01**: Ao terminar (sucesso ou abort), sistema exibe resumo final: total processadas, sucessos, erros, puladas
- [ ] **RESULT-02**: Se houver falhas, o resumo final exibe um aviso destacado listando cada empresa que falhou por código/nome

---

## v2 Requirements

### Usabilidade

- **US-01**: Ao concluir o lote com sucesso, abrir automaticamente a pasta de destino no Explorer
- **US-02**: Dialog de skip/abort ao falhar — em vez de pular automaticamente, perguntar à analista
- **US-03**: Relatório CSV consolidado do lote (empresa, resultado, qtd notas, erros)

---

## Out of Scope

| Feature | Motivo |
|---------|--------|
| Competência por empresa | Definida uma competência única para todo o lote |
| Processamento paralelo de empresas | Proibido — custo N8N e complexidade de tratamento de erros |
| Edição da planilha no app | Leitura apenas |
| Empresas de outros municípios | Somente GOIÂNIA por design |
| Seleção do arquivo de planilha | Caminho fixo em config.py |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PLAN-01 | Phase 1 | Complete |
| PLAN-02 | Phase 1 | Complete |
| PLAN-03 | Phase 1 | Complete |
| PLAN-04 | Phase 1 | Complete |
| PLAN-05 | Phase 1 | Complete |
| PROC-01 | Phase 2 | Pending |
| PROC-02 | Phase 2 | Pending |
| PROC-03 | Phase 2 | Pending |
| PROC-04 | Phase 2 | Pending |
| SELEC-01 | Phase 3 | Pending |
| SELEC-02 | Phase 3 | Pending |
| SELEC-03 | Phase 3 | Pending |
| SELEC-04 | Phase 3 | Pending |
| PROG-01 | Phase 3 | Pending |
| PROG-02 | Phase 3 | Pending |
| PROG-03 | Phase 3 | Pending |
| PROG-04 | Phase 3 | Pending |
| RESULT-01 | Phase 3 | Pending |
| RESULT-02 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-09*
*Traceability updated: 2026-03-09 — consolidated to 3 phases (coarse granularity)*
