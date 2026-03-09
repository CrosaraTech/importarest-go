# Codebase Concerns

**Analysis Date:** 2026-03-09

## Tech Debt

### Hardcoded Drive Paths (High Impact)

**Issue:** Application paths are hardcoded to G: drive, breaking on different machines or network changes.

**Files:**
- `config.py` (lines 6, 8)

**Impact:** Application cannot run on machines without G: drive access. Network maintenance, user transfers, or cloud migration will break the entire system. Deployment requires manual path editing per installation.

**Fix approach:**
- Replace hardcoded paths with environment variables or configuration file
- Use `.env` file pattern with fallback to default paths
- Add path validation on startup with user-friendly error messages
- Consider using `pathlib.Path` which handles path traversal better

**Current code:**
```python
BASE_DIR = Path(r"G:\Drives compartilhados\FISCAL\autmais\xml\Entradas\NFS-e")
RELATORIO_CSV = r"G:\Drives compartilhados\FISCAL\autmais\REST\Relatorio.csv"
URL_N8N = "https://joaomarcos1303.app.n8n.cloud/webhook/nfse-processing"
```

---

### Hardcoded N8N Webhook URL

**Issue:** N8N webhook URL is hardcoded with personal email domain, not environment-based.

**Files:** `config.py` (line 7)

**Impact:** URL cannot be changed without code modifications. Switching N8N instances, accounts, or deployments requires code edits. Production/staging environments cannot have different URLs.

**Fix approach:** Move to environment variable `N8N_WEBHOOK_URL` with validation

---

### Direct String Parsing for N8N Responses

**Issue:** Fallback parsing uses regex to extract JSON from text responses when JSON parsing fails.

**Files:** `services/processor.py` (lines 42-55: `_extrair_n8n_obj` function)

**Impact:** Fragile extraction logic if N8N response format changes. Silent failures when regex doesn't match expected pattern. Data loss without error visibility.

**Code:**
```python
def _extrair_n8n_obj(js, raw_text: str = ""):
    """Extrai o objeto principal da resposta N8N (list[0], dict ou regex fallback)."""
    if isinstance(js, list) and js and isinstance(js[0], dict):
        return js[0]
    if isinstance(js, dict):
        return js
    if raw_text:
        ext = {}
        for campo in ("ddd", "status", "motivo", "item_lc_original", "chave_nfse", "localidade"):
            m = re.search(rf'"{campo}"\s*:\s*"(.*?)"', raw_text, re.DOTALL)
            # Fragile regex parsing instead of proper error handling
```

**Fix approach:**
- Add comprehensive logging when regex fallback is triggered
- Validate extracted values match expected format
- Return clear error status instead of partial data
- Consider making N8N response validation stricter

---

### Magic String Indices for Response Parsing

**Issue:** Response lines are split by `;` and accessed by hard-coded indices without validation.

**Files:** `services/processor.py` (lines 268-276, 308-318, 364-374)

**Impact:** IndexError risks when N8N response format changes. Silent failures if fields shift. No validation that expected fields exist before access.

**Code:**
```python
partes = res_ia.split(";")
_lc_ia = normalize_digits(partes[19]) if len(partes) > 19 else ""
# If N8N changes order or adds fields, index 19 may be wrong
```

**Fix approach:**
- Define response schema/contract with named fields
- Create response parser class that validates field count and order
- Validate N8N response against expected format before processing
- Add detailed logging of what index was accessed

---

## Known Bugs

### Zip File XML Extraction Encoding

**Issue:** ZIP file entries are decoded with `errors="ignore"`, silently dropping non-UTF-8 characters.

**Files:** `services/processor.py` (line 157)

**Impact:** Characters in company names, addresses, or descriptions may be silently corrupted. User won't know data was lost. TXT file will have incomplete information.

**Code:**
```python
dict_xmls[n] = z.read(n).decode("utf-8", errors="ignore")
```

**Fix approach:**
- Try UTF-8 first, then fall back to ISO-8859-1 or CP1252 with explicit warning
- Log when characters are dropped
- Display warning to user if encoding fallback occurs

---

### Windows Font Paths Fallback Chain

**Issue:** Circular progress indicator tries to load fonts from hardcoded Windows font paths but silently degrades if unavailable.

**Files:** `ui/components.py` (lines 11-16, 49-54)

**Impact:** On systems with non-standard Windows font paths (non-English Windows or custom installations), the progress indicator may not render text properly. Silent failure masks the problem.

**Code:**
```python
_FONT_PATHS = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    # ...hardcoded paths
]

for path in _FONT_PATHS:
    try:
        return ImageFont.truetype(path, size_px)
    except Exception:
        pass  # Silent failure
```

**Fix approach:**
- Use `tkinter.font.families()` to detect available fonts
- Fall back to system default fonts programmatically
- Log which font was loaded for debugging

---

## Security Considerations

### N8N Webhook URL Exposure

**Issue:** N8N webhook URL is hardcoded in source code and visible in version control.

**Files:** `config.py` (line 7)

**Impact:** Anyone with access to code can hit the webhook. If webhook processes sensitive data, there's no authentication shown. Credentials are in plaintext in history.

**Current mitigation:** None evident (URL is in code)

**Recommendations:**
- Move to environment variable with validation
- Implement webhook signature verification in N8N
- Consider API key-based authentication instead of just URL
- Remove from git history: `git filter-branch` or `bfg-repo-cleaner`

---

### Missing Input Validation on User Inputs

**Issue:** Company code and vigência inputs lack validation before filesystem operations.

**Files:** `ui/app.py` (lines 154-160, 155-156)

**Impact:** Invalid codes could cause errors or unexpected behavior. No path traversal protection visible. Vigência format isn't validated before string use.

**Code:**
```python
codigo = self.ent_codigo.get().strip()
vigencia = self.ent_vigencia.get().strip()

if not codigo or not vigencia:
    messagebox.showwarning(...)
    # But no format validation after this
```

**Recommendations:**
- Validate `codigo` format (alphanumeric, max length)
- Validate `vigencia` matches MMYYYY format with regex
- Sanitize inputs before path construction
- Use `pathlib.Path` which handles path traversal better

---

### Error Messages May Leak Sensitive Data

**Issue:** Exception messages are displayed directly in messageboxes without sanitization.

**Files:** `ui/app.py` (lines 225-227)

**Impact:** Stack traces, file paths, or internal errors could be shown to users. May leak configuration or system information.

**Code:**
```python
except Exception as e:
    messagebox.showerror("Erro", f"Erro inesperado:\n\n{e}")  # Raw exception text
```

**Recommendations:**
- Sanitize error messages before display
- Log full stack trace to file for debugging
- Show user-friendly messages only

---

## Performance Bottlenecks

### Synchronous Network Calls Block UI

**Issue:** N8N API calls use synchronous `requests.post()` in worker thread but UI thread waits for results.

**Files:** `services/n8n_client.py` (line 7)

**Impact:** Long network timeouts (150s) can freeze UI. If network is slow or N8N is down, users see unresponsive application. No timeout feedback during long operations.

**Code:**
```python
def chamar_n8n(payload: dict, timeout: int = 150):
    return requests.post(URL_N8N, json=payload, timeout=timeout)  # Blocking
```

**Improvement path:**
- Add connection timeout separate from read timeout
- Implement retry logic with exponential backoff
- Add UI feedback during network wait (show elapsed time)
- Consider async requests or timeout warning dialog

---

### IBGE API Queries Not Cached Across Sessions

**Issue:** Municipal code to name mapping is cached only in memory (`_ibge_cache`), lost on application restart.

**Files:** `services/ibge.py` (lines 5, 19, 23)

**Impact:** Repeated queries for same municipalities make unnecessary network requests. Slower performance on cold starts. Network dependency for common operations.

**Code:**
```python
_ibge_cache: dict = {}  # Only in-memory, lost on restart
```

**Improvement path:**
- Persist cache to local SQLite or JSON file
- Implement cache TTL (refresh weekly)
- Show cache hit/miss stats in logs

---

### XML Parsing Not Optimized for Large Files

**Issue:** Full XML trees are parsed into memory even if only a few fields are needed.

**Files:** `core/extractor.py` - uses `ET.fromstring()` for entire XML before extraction

**Impact:** Large XML files (>10MB) may cause memory issues. No streaming parser. Each extraction iterates entire tree multiple times.

**Improvement path:**
- Use iterative parsing (`ET.iterparse()`) for large files
- Cache parsed trees temporarily during multi-pass extraction
- Consider SAX parser for streaming-only scenarios

---

## Fragile Areas

### Complex N8N Response State Machine

**Files:** `services/processor.py` (entire processor class, ~693 lines)

**Why fragile:**
- Multiple processing paths (extract, map_only, goiania, local) with overlapping logic
- Response status strings ("manual_review", "manual_fill_itemlc_ddd", "manual_review_map_only") are magic strings
- Retry logic (_processar_map_only_retry) duplicates extraction/validation code
- Changes to N8N response format require edits in multiple places

**Safe modification:**
- Define response schema as constants/enums
- Extract common validation logic into reusable methods
- Add response type validation early in processing chain
- Write integration tests against actual N8N responses

**Test coverage gaps:** No visible unit tests for processor state transitions. Retry path (_processar_map_only_retry) likely untested.

---

### XML Field Path Selection Logic

**Issue:** Multiple XPath expressions tried in sequence with fallback defaults.

**Files:** `core/extractor.py` (lines 14-26 and similar patterns repeated ~40 times)

**Why fragile:**
- If XML structure varies unexpectedly, wrong field gets extracted
- No validation that extracted value makes sense (e.g., CNPJ is 14 digits)
- Error message in detector function ("desconhecido" pattern) doesn't indicate which extraction failed

**Code:**
```python
codigo_municipio = find_text(root, [
    ".//{*}OrgaoGerador//{*}CodigoMunicipio",
    ".//{*}InfNfse//{*}OrgaoGerador//{*}CodigoMunicipio",
    ".//{*}PrestadorServico//{*}Endereco//{*}CodigoMunicipio",
    # ... 7 more paths
], default="")
```

**Safe modification:**
- Add field-level validation (e.g., municipio code must be 7 digits)
- Log which path matched for debugging
- Return extraction with confidence score
- Fall back to N8N extraction if validation fails

---

### Manual Review Dialog Data Flow

**Issue:** Data passed between processor and UI dialog uses plain dicts without clear schema.

**Files:** `services/processor.py` (lines 526-537, 553-582) and `ui/dialogs.py` (lines 106-265)

**Why fragile:**
- No validation that required fields exist in dados_base
- Field names vary between contexts ("item_lc_original" vs "descricao_servico")
- from_n8n flag changes behavior but is not well documented

**Safe modification:**
- Create DataClass for manual review data with required fields
- Validate data structure before passing to UI
- Document expected fields and their sources

---

## Scaling Limits

### Single-Threaded UI Processing

**Issue:** Application processes notes sequentially in worker thread, but all UI updates must go through main thread.

**Files:** `ui/app.py` (lines 176-180, 182-228)

**Current capacity:** Process ~100 notes per minute (estimated from 150s timeout per N8N call)

**Limit:** Processing 1000+ notes will take 15+ minutes with no parallelization.

**Scaling path:**
- Implement note queue with parallel N8N requests (5-10 concurrent)
- Pool requests to reduce total time
- Add batch processing mode for large imports
- Consider moving heavy lifting to background job queue (Celery, Bull)

---

### CSV Report Written All at Once

**Issue:** Report is assembled in memory then written in one operation.

**Files:** `services/report.py` (lines 11-19)

**Impact:** Large imports (10k+ notes) could use significant memory. No streaming output. Report is inaccessible until processing completes.

**Improvement path:**
- Stream rows to CSV as notes are processed
- Allow user to view partial reports while processing continues
- Use generator pattern for report rows

---

## Dependencies at Risk

### N8N Dependency on External Cloud Service

**Issue:** Application is completely dependent on `joaomarcos1303.app.n8n.cloud` webhook being available.

**Impact:**
- If N8N goes down, entire application is non-functional
- No fallback extraction logic
- No local classification capability as backup

**Current mitigation:** None visible (no fallback mode)

**Migration plan:**
- Implement minimal local classification as fallback (simple keyword matching for common services)
- Support self-hosted N8N instance as alternative
- Document N8N setup so it can be moved if needed
- Add health check endpoint to verify N8N is reachable on startup

---

### Supabase Vector Store Dependency

**Issue:** LC 116 classification depends on Supabase vector store for semantic search.

**Files:** README.md (lines 156-159) mentions Supabase integration in N8N workflow

**Impact:** If Supabase is unavailable or vectors are stale, classification fails. No embedded local model as backup.

**Risk:** N8N workflow failure not clearly surfaced in Python code, may cause opaque errors.

**Recommendations:**
- Document Supabase configuration requirements
- Add N8N health check before processing starts
- Implement local fallback classification (regex/keywords)

---

## Missing Critical Features

### No Offline Mode

**Issue:** Application requires network access for:
1. N8N webhook (mandatory)
2. IBGE municipal lookup (for city names)
3. ViaCEP lookups (in N8N for addresses)

**Problem:** Cannot process XMLs if internet is down or services are unavailable.

**Impact:** Frequent business interruptions in case of ISP issues, API downtime, or network problems.

**Solution:**
- Cache municipal data locally on first run
- Implement local classification fallback
- Allow batch processing to be queued offline and synced later

---

### No Batch Processing or CLI Interface

**Issue:** Only interactive GUI mode exists, no CLI or batch processing.

**Files:** `main.py` - only entry point is GUI

**Problem:** Cannot integrate with automated workflows or schedule processing. Must run manually.

**Solution:**
- Add CLI interface with `argparse` for headless processing
- Support batch file listing (--folder, --pattern)
- Output machine-readable format (JSON option)

---

### No Validation Report for Data Quality

**Issue:** While CSV report shows processing status, no data quality validation.

**Problem:**
- Generated TXT files may have invalid data
- No checks for missing mandatory fields
- No format validation before REST import

**Solution:**
- Add pre-import validation: verify all lines have required fields
- Check date formats, numeric ranges
- Warn if Item LC is in manual review state
- Generate validation report before download

---

## Test Coverage Gaps

### Processor State Machine Untested

**What's not tested:**
- Extract mode path with IA failure scenarios
- Map-only retry logic
- Goiânia MEI-specific processing
- Manual review response handling

**Files:** `services/processor.py` (entire class)

**Risk:** State transitions are complex and fragile. Changes may break specific scenarios unnoticed.

**Priority:** High - add unit tests for each processing mode

---

### XML Parsing Edge Cases

**What's not tested:**
- Unknown XML namespaces/formats
- Malformed ZIP files
- Empty or minimal XMLs
- Mixed pattern XMLs (both ABRASF and Nacional in same batch)

**Files:** `core/xml_parser.py`, `services/processor.py` (_carregar_xmls, _separar_eventos)

**Risk:** Edge cases silently fail or produce incomplete data.

**Priority:** Medium - add property-based tests for XML variants

---

### UI Dialog Form Validation

**What's not tested:**
- Manual Item LC entry validation (exactly 4 digits)
- DDD entry validation (exactly 2 digits)
- Header dialog IM and Razão Social requirements
- Error message display and user recovery flow

**Files:** `ui/dialogs.py` (lines 242-265)

**Risk:** User can enter invalid data that silently corrupts output.

**Priority:** Medium - add integration tests for dialog interactions

---

### N8N Integration Contract

**What's not tested:**
- Expected response format validation
- Timeout behavior
- Failure response handling
- Retry scenarios

**Files:** `services/n8n_client.py`, `services/processor.py` (N8N call sections)

**Risk:** Changes to N8N response format break silently.

**Priority:** High - add integration tests with mock N8N responses

---

## Code Quality Issues

### Exception Handling Too Broad

**Issue:** Many `except Exception:` blocks catch everything without discrimination.

**Files:** `services/processor.py` (lines 282, 322, 392, 457, 499), `core/extractor.py` (line 290), `ui/components.py` (line 52, 105)

**Impact:** Programming errors (like typos in variable names) are silently caught and logged as business errors. Harder to debug.

**Example:**
```python
except Exception as e:
    self._log(f"❌ Erro ao processar nota {nome}: {e}")
    relatorio.append(_relatorio_row(nome, dados, "Erro", "extract", str(e)))
    # Generic catch masks programming bugs
```

**Fix approach:**
- Catch specific exceptions: `requests.RequestException`, `ET.ParseError`, `KeyError`, etc.
- Let programming errors (AttributeError, TypeError) propagate for debugging
- Add logging with `traceback.format_exc()` for caught exceptions

---

### Inconsistent Logging Levels

**Issue:** All logging goes through single `log()` method in UI with emoji-based color coding, no structured logging levels.

**Files:** `ui/app.py` (lines 136-148)

**Impact:** Cannot filter by severity. Cannot programmatically consume logs. Emoji parsing is fragile.

**Fix approach:**
- Implement proper logging with `logging` module (DEBUG, INFO, WARNING, ERROR levels)
- Allow log file output
- Make emoji optional for non-interactive mode

---

### Magic Numbers and Strings Throughout

**Issue:** Configuration constants appear as literals scattered throughout code.

**Examples:**
- "2" and "4" for REST modelo type
- ";", "@", "_" as delimiters
- "ABRASF", "nacional", "desconhecido" as status strings
- 85, 75 as confidence thresholds (in README/N8N workflow)

**Files:** Multiple files (too many to list)

**Impact:** Impossible to find all uses of a constant. Changes require multiple edits. Typos risk.

**Fix approach:**
- Create `constants.py` with all magic values
- Define enums for status values
- Use type hints to enforce proper values

---

*Concerns audit: 2026-03-09*
