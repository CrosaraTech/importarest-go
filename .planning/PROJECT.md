# ImportaREST GO

## What This Is

Aplicativo desktop Windows (Python/Tkinter) para importação de NFS-e em XML, gerando arquivos TXT no formato REST para envio à prefeitura. Usado por analistas fiscais que processam notas de múltiplas empresas mensalmente. O processamento combina extração local de XML com pipeline de IA via N8N/GPT-4o-mini para classificação de campos fiscais.

## Core Value

Analistas geram arquivos REST de NFS-e com o mínimo de intervenção manual — individualmente ou em lote por competência.

## Requirements

### Validated

<!-- Funcionalidades existentes e em produção -->

- ✓ Analista informa código da empresa + competência (MMAAAA) e gera TXT REST a partir de XMLs NFS-e — existente
- ✓ Sistema detecta automaticamente o padrão XML (ABRASF vs Nacional) — existente
- ✓ Pipeline N8N/GPT-4o-mini classifica e valida campos fiscais — existente
- ✓ Sistema gera relatório CSV de auditoria por processamento — existente
- ✓ UI exibe progresso e permite revisão manual de documentos incompletos — existente

### Active

<!-- Funcionalidade nova: processamento em lote -->

- [ ] Sistema lê automaticamente a planilha fixa `G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx` (colunas A=COD, D=ANALISTA)
- [ ] Analista seleciona seu nome na lista de analistas extraída da coluna D
- [ ] Analista informa uma competência (mês/ano) que será aplicada a todas as empresas do lote
- [ ] Analista escolhe a pasta de destino onde todos os TXTs do lote serão salvos
- [ ] Sistema processa todas as empresas da analista em sequência, sem intervenção entre elas
- [ ] UI exibe durante o lote: barra de progresso (X/Y empresas), nome da empresa atual, estimativa de tempo restante, e log de resultado por empresa
- [ ] Quando uma empresa falha, o sistema pausa e pergunta se a analista quer pular e continuar ou abortar o lote
- [ ] Modo lote coexiste com o fluxo individual existente — é uma opção adicional, não substitui o fluxo atual

### Out of Scope

- Competência por empresa no lote — definida uma competência única para todo o lote
- Seleção de arquivo de planilha — caminho é fixo em `G:\Drives compartilhados\FISCAL\...`
- Processamento paralelo de empresas — processamento é sempre sequencial para evitar sobrecarga do N8N
- Edição da planilha dentro do app — leitura apenas

## Context

- Planilha de referência: `G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx` — colunas relevantes: A (COD), D (ANALISTA)
- A planilha pode ter outras colunas (CNPJ, razão social, etc.) que devem ser ignoradas
- O fluxo individual existente usa código da empresa + competência como entrada — o lote reutiliza esse mesmo mecanismo por empresa
- N8N webhook tem custo por chamada — processamento sequencial é intencional
- Aplicativo roda em Windows, caminhos são Windows paths

## Constraints

- **Tech Stack**: Python 3.10+ / ttkbootstrap — manter compatibilidade com stack existente
- **Planilha**: `openpyxl` para leitura de XLSX (adicionar dependência se necessário)
- **N8N**: Processamento sequencial — não paralelizar chamadas ao webhook
- **UI**: Modo lote deve ser acessível da janela principal sem substituir os controles existentes

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Caminho da planilha fixo no código (config.py) | Mesmo padrão usado para outros caminhos fixos no projeto | — Pending |
| Processamento sequencial (não paralelo) | Evitar sobrecarga do N8N e facilitar tratamento de erros | — Pending |
| Modo lote como aba ou seção separada na UI | Separação clara sem quebrar fluxo individual | — Pending |

---
*Last updated: 2026-03-09 after initialization*
