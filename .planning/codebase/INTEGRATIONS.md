# External Integrations

**Analysis Date:** 2026-03-09

## APIs & External Services

**N8N Workflow Automation:**
- N8N Cloud - AI-powered NFS-e processing pipeline
  - SDK/Client: `requests` HTTP POST to webhook
  - Endpoint: `https://joaomarcos1303.app.n8n.cloud/webhook/nfse-processing`
  - Auth: Webhook URL (no additional auth token visible)
  - Implementation: `services/n8n_client.py` - `chamar_n8n(payload, timeout=150)`

**IBGE Location Data:**
- IBGE Localidades API - Municipality lookup and validation
  - SDK/Client: `requests`
  - Endpoint: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo_municipio}`
  - Auth: None (public API)
  - Implementation: `services/ibge.py` - `consulta_cidade_ibge(codigo_municipio)`
  - Caching: In-memory cache dictionary to reduce API calls

## Data Storage

**Databases:**
- None directly. Data is:
  - Input: XML files from shared Google Drive path (`G:\Drives compartilhados\FISCAL\autmais\xml\Entradas\NFS-e`)
  - Output: Text files and CSV reports

**File Storage:**
- Google Drive (shared network path) - NFS-e XML input directory
  - Path: `G:\Drives compartilhados\FISCAL\autmais\xml\Entradas\NFS-e`
  - Access: Mounted network drive (Windows SMB)

**Report Storage:**
- Local CSV via filesystem
  - Path: `G:\Drives compartilhados\FISCAL\autmais\REST\Relatorio.csv`
  - Format: `;` delimited CSV with columns: Arquivo, CNPJ Prestador, Numero Nota, Valor Documento, Status, Modo, Detalhe, Chave NFS-e, Data/Hora Execucao, Linha TXT

**Caching:**
- In-memory dictionary cache for IBGE municipality lookups
- Located in: `services/ibge.py` - `_ibge_cache`

## Authentication & Identity

**Auth Provider:**
- None explicitly implemented (no user authentication)
- N8N credentials: OpenAI API key, Supabase URL/key, HuggingFace API key configured in N8N workflow (not in Python app)

**Service Credentials:**
- Environment variables (referenced in `.gitignore`, not committed):
  - `.env` file containing sensitive credentials
  - `certificados.json` - May contain certificate data (in `.gitignore`)

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry, LogRocket, etc.)

**Logs:**
- Console output via `print()` and UI logging
- UI Status Display: `JanelaCrosara.log()` method shows status messages with emoji indicators
- Report Output: CSV file (`gravar_relatorio()` in `services/report.py`)

**Logging Indicators:**
- Success: ✅ ✨ 🏁
- Error: ❌
- Warning: ⚠️
- Processing: 🤖 🔁 🔄

## CI/CD & Deployment

**Hosting:**
- Desktop Windows application (local execution)
- N8N Cloud - Hosted workflow engine
  - URL: `joaomarcos1303.app.n8n.cloud`

**CI Pipeline:**
- None detected

**Deployment:**
- Manual: `python main.py` execution on Windows machine

## Environment Configuration

**Required env vars:**
- Not explicitly defined in code, but `.env` file referenced in `.gitignore`
- Likely includes:
  - N8N webhook URL (hardcoded in config.py as `URL_N8N`)
  - OpenAI API key (for N8N workflow)
  - Supabase URL and key (for vector store)
  - HuggingFace API key (for embeddings)

**Base Configuration (hardcoded in `config.py`):**
- `BASE_DIR` - XML input directory path
- `URL_N8N` - N8N webhook endpoint
- `RELATORIO_CSV` - Report output path
- `IBGE_MUN_URL` - IBGE API endpoint template
- `GOIANIA_IBGE_7` - City code 5208707
- `GOIANIA_IBGE_6` - City code 520870
- `GOIANIA_DDD` - Area code 62

**Secrets location:**
- `.env` file (local, not committed)
- `certificados.json` (local, not committed)

## N8N Workflow Pipeline

**Workflow Location:** `/c/Users/Havai/Desktop/Rest iss.net/Workflow N8N/` and `n8n/workflow.json`

**Workflow Modes:**

1. **Extract Mode** - Full XML parsing by AI:
   - Input: Raw XML + "extract" mode
   - Process:
     - GPT-4o-mini extracts all fiscal fields from XML
     - Confidence check (≥85%)
     - ViaCEP address enrichment
     - LC 116 item classification
   - Output: Complete line in TXT format or manual_review request

2. **Map Only Mode** - Service classification only:
   - Input: Pre-extracted data from Python + "map_only" mode
   - Process:
     - ViaCEP address lookup
     - LC 116 item classification (confidence ≥75%)
   - Output: DDD + Item LC or manual_review_map_only request

**N8N Nodes (from workflow.json):**
- `Receber Webhook NFS-e` - POST webhook receiver
- `Modo: Extract ou Map Only?` - Switch logic
- `IA Extrair Dados do XML` - GPT-4o-mini XML extraction
- `Confiança Extração ≥ 85?` - Confidence validation
- `Consultar Endereço (ViaCEP)` - Address enrichment
- `IA Classificar Item LC 116` - Service classification with Supabase semantic search
- `Montar Linha TXT Final` - Line assembly (extract mode)
- `Montar Resposta: DDD + Item LC` - Response assembly (map_only mode)
- `Montar Erro: Manual Review` - Fallback for low confidence

**External Services Used by N8N:**
- OpenAI GPT-4o-mini (temperature: 0 for precision)
- Supabase Vector Store (semantic search on LC 116 items)
- HuggingFace Embeddings (vector generation for semantic search)
- ViaCEP API (Brazilian address lookup)
- Google Drive (JSON base LC 116 ingestion pipeline)

## Webhooks & Callbacks

**Incoming:**
- N8N webhook endpoint: `https://joaomarcos1303.app.n8n.cloud/webhook/nfse-processing`
  - Method: POST
  - Payload: JSON with XML data, mode (extract/map_only), and extracted fields
  - Response: JSON with classification result or manual_review request

**Outgoing:**
- None detected (application makes requests, doesn't expose endpoints)

## Data Flow - NFS-e Processing Pipeline

```
1. User Interface (Tkinter)
   ↓ [empresa_cod, vigencia, gerar_mei flag]
   ↓
2. WorkflowProcessor.processar() [services/processor.py]
   ↓ [reads XML files from BASE_DIR]
   ↓
3. XML Parsing
   ├─ eh_evento_cancelamento() [core/xml_parser.py] - Skip cancellations
   ├─ detectar_padrao_nfse() [core/xml_parser.py] - Detect ABRASF or Nacional
   ├─ extrair_dados_python() [core/extractor.py] - Extract 50+ fields locally
   └─ Call N8N webhook [services/n8n_client.py]
   ↓
4. N8N Pipeline (Cloud)
   ├─ Extract mode: Full AI parsing + classification
   └─ Map only mode: Classification only (DDD + Item LC)
   ↓
5. Response Processing
   ├─ Parse N8N response
   ├─ Handle manual_review fallback
   └─ consulta_cidade_ibge() [services/ibge.py] - Validate municipality
   ↓
6. TXT Generation
   ├─ montar_cabecalho() [core/txt_builder.py]
   ├─ montar_linha_txt() [core/txt_builder.py]
   └─ Handle wrong vigency (separate files)
   ↓
7. Report & Output
   ├─ gravar_relatorio() [services/report.py] - CSV report
   └─ User downloads TXT for REST import
```

---

*Integration audit: 2026-03-09*
