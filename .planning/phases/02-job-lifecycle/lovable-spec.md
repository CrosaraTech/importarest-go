# ImportaREST GO — Lovable Frontend Specification

> Paste this entire document into Lovable to generate the React app.
> This spec covers authentication, the upload form (FRNT-01), and the job progress dashboard (FRNT-02).

---

## 1. App Overview

**App name:** ImportaREST GO
**Purpose:** Analysts upload NFS-e XML files and monitor ISS.NET import processing in real time.
**Users:** Internal accountants / analysts on office desktops (desktop-first layout).
**Stack:** React + TypeScript, Vite, TailwindCSS, Supabase JS client (auth), TanStack Query (data fetching).

---

## 2. Environment Variables

Set these in `.env` (Vite project):

```
VITE_SUPABASE_URL=https://<your-project>.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_...
VITE_API_URL=http://localhost:8000
```

> **CORS note:** The backend reads `ALLOWED_ORIGINS` from its `.env`.
> Add this app's origin (e.g. `https://yourapp.lovable.app` or `http://localhost:5173`)
> to the backend's `ALLOWED_ORIGINS` comma-separated list.

---

## 3. App Structure & Routing

```
/               → redirect to /upload if authenticated, else to /login
/login          → Supabase Auth login/signup page
/upload         → Upload Form (FRNT-01) — protected
/jobs/:jobId    → Job Progress (FRNT-02) — protected
```

**Protected route wrapper:** If `supabase.auth.getSession()` returns no session, redirect to `/login`.

**Auth state:** Use `supabase.auth.onAuthStateChange` to update session in React context or a global store.

### Supabase client initialisation

```ts
import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)
```

### API helper — attach JWT to every request

```ts
async function apiRequest(path: string, init?: RequestInit) {
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''
  return fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  })
}
```

---

## 4. Login Page

- Use Supabase Auth UI component (`@supabase/auth-ui-react`) with `Auth` component and `ThemeSupa` appearance, OR build a minimal email+password form that calls `supabase.auth.signInWithPassword(...)`.
- On successful login, redirect to `/upload`.
- Show a signup link: call `supabase.auth.signUp(...)`.
- Page should be centered, card style, 400px max width, white card on light-gray background.

---

## 5. Upload Form Page (FRNT-01)

**Route:** `/upload`

### 5.1 Page layout

Full-page centered form card (max-width 600px), white background, subtle shadow.
Header: "Importar NFS-e" in bold, 24px.
Logout link (top-right of page or nav bar).

### 5.2 Company selector (required)

```
Label: Empresa
Type: <select> dropdown (native or Shadcn/ui Select)
```

On page load, fetch:

```
GET /companies
Authorization: Bearer {access_token}
```

Response shape:
```json
{
  "companies": [
    {
      "cod": "001",
      "nome_empresa": "Acme Ltda",
      "municipio": "Goiania",
      "analista": "joao",
      "is_mine": true
    }
  ]
}
```

**Display:** Filter to show only `is_mine === true` companies.
**Option text format:** `{cod} - {nome_empresa} ({municipio})`
**Value:** `cod` field.
If no companies returned, show: "Nenhuma empresa atribuida a voce. Contate o administrador."
Loading state: show a spinner or "Carregando..." placeholder.

### 5.3 Vigencia input (required)

```
Label: Vigencia (MM/AAAA)
Type: text input with mask or two dropdowns
```

**Preferred:** Two adjacent dropdowns:
- Month dropdown: "01 - Janeiro" through "12 - Dezembro"
- Year dropdown: current year ± 2 years

**Alternative:** Single text input with pattern `MM/YYYY` and HTML pattern validation `^(0[1-9]|1[0-2])\/\d{4}$`.

The value sent to the API must be the string `"MM/YYYY"` (e.g. `"03/2026"`).

### 5.4 MEI toggle

```
Label: Gerar MEI
Type: checkbox or toggle switch
Default: unchecked (false)
```

Boolean value sent as `gerar_mei` form field.

### 5.5 File upload zone

```
Label: Arquivos NFS-e
Accept: .xml, .zip
Multiple: true
```

Drag-and-drop area with:
- Border: dashed, 2px, gray-300, rounded-lg
- Idle state: "Arraste arquivos .xml ou .zip aqui, ou clique para selecionar"
- Drag-over state: highlight border in primary orange, light orange background
- After selection: list each file name below the drop zone (with an X to remove)

**Validation rules (show inline errors):**
- Only `.xml` and `.zip` extensions accepted
- Files must not be empty

**Note to user:** "Aceita multiplos XMLs ou um unico ZIP."

### 5.6 Submit button

```
Text: "Processar"
Style: full width, primary orange background (#E58A4E), white text, bold
Disabled state: while uploading or if required fields are empty
Loading state: spinner + "Enviando..."
```

### 5.7 Form submission

Build a `FormData` object:

```ts
const formData = new FormData()
files.forEach(f => formData.append('files', f))
formData.append('emp_cod', selectedCompanyCod)
formData.append('vigencia', vigenciaString)          // e.g. "03/2026"
formData.append('gerar_mei', gerar_mei ? 'true' : 'false')

const res = await apiRequest('/jobs', {
  method: 'POST',
  body: formData,
  // Do NOT set Content-Type manually — browser sets multipart boundary
})
```

**On 200 success:**
```json
{ "job_id": "abc123def456", "status": "queued" }
```
Redirect to `/jobs/{job_id}`.

**On 422 error:**
```json
{ "detail": "Invalid file type for 'readme.txt'. Only .xml and .zip are accepted." }
```
Show `detail` string as red inline error below the file zone.

**On 409 conflict:**
```json
{ "detail": "Analyst joao already has an active job ..." }
```
Show as amber/yellow toast or banner: "Voce ja tem um job ativo. Aguarde a conclusao antes de enviar novos arquivos."

**On other errors:** Show generic error: "Erro ao enviar. Tente novamente."

---

## 6. Job Progress Page (FRNT-02)

**Route:** `/jobs/:jobId`

### 6.1 Page layout

Full-page, centered card (max-width 700px), white background.
Header: "Processando — {emp_cod} / {vigencia}" or "Job {jobId}" if parameters not available.
Back link: "← Novo upload" navigates to `/upload`.

### 6.2 Polling

Poll `GET /jobs/{jobId}/status` every **2500ms** using TanStack Query:

```ts
const { data } = useQuery({
  queryKey: ['job-status', jobId],
  queryFn: async () => {
    const res = await apiRequest(`/jobs/${jobId}/status`)
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  refetchInterval: (data) =>
    data?.status === 'completed' || data?.status === 'failed' ? false : 2500,
})
```

Stop polling when `status === "completed"` or `status === "failed"`.

### 6.3 Status badge

```
queued    → gray badge,   text: "Na fila"
running   → blue badge,   text: "Processando"
completed → green badge,  text: "Concluido"
failed    → red badge,    text: "Falhou"
```

Style: pill shape, 12px font, uppercase, colored background.

### 6.4 Progress bar

```
Height: 12px, rounded-full
Track: gray-200
Fill: primary orange (#E58A4E) for running, green (#28A745) for completed
Label above bar: "X de N notas processadas" (uses current_note and total_notes from response)
Percent label: show `percent`% to the right or below
```

When `total_notes === 0`, show indeterminate animation (pulse or shimmer).

### 6.5 Log stream

Scrollable container, max-height 300px, `overflow-y: auto`, dark background (`gray-900`), monospace font, 13px.

Render each entry from `recent_logs` array (last 20 entries, newest at bottom):

```
✅  → green text  (log starts with "✅" or contains "sucesso"/"concluido")
❌  → red text    (log starts with "❌" or contains "erro"/"falhou")
⚠️  → amber text  (log starts with "⚠️" or contains "aviso")
🤖  → blue text   (log starts with "🤖" or info-level messages)
     default → gray-300 text
```

Auto-scroll: whenever `recent_logs` updates, scroll the container to the bottom.

Empty state (no logs yet): "Aguardando logs..." in gray-500 italic.

### 6.6 Error section

Only render when `errors` array is non-empty.

Collapsible section titled: "Erros ({count})" with a red icon.
Expand/collapse with chevron toggle.
Each error item in a red-tinted row (red-50 background, red-800 text):

```
errors is list[str] — display each string directly as an error line
```

### 6.7 Terminal states

**On completed:**
```
Green checkmark icon + "Processamento concluido com sucesso!"
Subtitle: "X notas processadas."
```
(Phase 4 will add download buttons here — leave a placeholder comment.)

**On failed:**
```
Red X icon + "Processamento falhou."
Show errors section expanded by default if errors is non-empty.
```

---

## 7. API Contract Reference

All requests require: `Authorization: Bearer {supabase_access_token}`

---

### GET /companies

**Query params (all optional):**
| Param | Type | Description |
|---|---|---|
| analyst | string | Filter by `analista` column value |
| municipio | string | Filter by `municipio` column |

**Response 200:**
```json
{
  "companies": [
    {
      "cod": "001",
      "nome_empresa": "Empresa Exemplo Ltda",
      "municipio": "Goiania",
      "cnpj": "12.345.678/0001-99",
      "analista": "joao",
      "is_mine": true
    }
  ]
}
```

Frontend usage: fetch all companies, filter client-side on `is_mine === true` for the dropdown.

---

### POST /jobs

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| files | File (multiple) | Yes | .xml or .zip files (empty files rejected) |
| emp_cod | string | Yes | Company code (e.g. "001") |
| vigencia | string | Yes | Competence period as "MM/YYYY" (e.g. "03/2026") |
| gerar_mei | boolean | No | Whether to generate MEI lines (default false) |

**Response 200:**
```json
{ "job_id": "abc123def456", "status": "queued" }
```

**Response 422** (invalid file or missing fields):
```json
{ "detail": "Invalid file type for 'readme.txt'. Only .xml and .zip are accepted." }
```

**Response 409** (analyst already has active job):
```json
{ "detail": "Analyst joao already has an active job abc123" }
```

---

### GET /jobs/{job_id}/status

**Path param:** `job_id` — the hex string returned by POST /jobs.

**Response 200:**
```json
{
  "job_id": "abc123def456",
  "status": "running",
  "current_note": 12,
  "total_notes": 47,
  "percent": 25.53,
  "recent_logs": [
    "✅ Nota 001-2026-00001 processada com sucesso",
    "✅ Nota 001-2026-00002 processada com sucesso",
    "❌ Nota 001-2026-00003 — CNPJ invalido"
  ],
  "errors": [
    "Nota 001-2026-00003 — CNPJ invalido"
  ],
  "result_ready": false
}
```

**status values:** `"queued"` | `"running"` | `"completed"` | `"failed"`

**Response 403** (job belongs to different user): redirect to `/upload` with error toast.
**Response 404** (unknown job_id): show "Job nao encontrado." and link back to `/upload`.

---

## 8. Styling Guidance

### Color palette

| Token | Hex | Usage |
|---|---|---|
| Primary | `#E58A4E` | Buttons, progress fill, active states |
| Success | `#28A745` | Completed badge, success messages |
| Error | `#C0392B` | Failed badge, error text |
| Warning | `#F39C12` | Queued/amber states |
| Info | `#3498DB` | Running badge, info logs |
| Text | `#2C3E50` | Primary text |
| BG | `#F8F9FA` | Page background |

### Typography

- Body: system font stack (Tailwind default)
- Log stream: `font-mono` Tailwind class, 13px
- Page titles: 24px bold
- Labels: 14px medium, gray-700

### Layout notes

- Desktop-first: min-width 1024px assumed, no hamburger menus needed
- Form card: `max-w-xl mx-auto mt-10 p-8 bg-white rounded-xl shadow-md`
- Progress card: `max-w-2xl mx-auto mt-10 p-8 bg-white rounded-xl shadow-md`
- Use 8px spacing grid (Tailwind `gap-2`, `gap-4`, `gap-8`)

---

## 9. Component Checklist for Lovable

Generate the following components:

- [ ] `SupabaseProvider` — auth context, session state, signOut helper
- [ ] `ProtectedRoute` — redirects unauthenticated users to `/login`
- [ ] `LoginPage` — email/password form with Supabase auth
- [ ] `UploadForm` — company selector, vigencia, MEI toggle, file zone, submit
- [ ] `CompanySelector` — fetches GET /companies, filters is_mine, renders dropdown
- [ ] `FileDropzone` — drag-and-drop zone with file list and remove buttons
- [ ] `JobProgress` — polling, status badge, progress bar, log stream, errors
- [ ] `StatusBadge` — colored pill for job status
- [ ] `LogStream` — scrollable monospace log viewer with emoji-to-color mapping
- [ ] `ErrorList` — collapsible error section with count

---

## 10. Known Limitations (v1)

- Only one active job per analyst at a time (backend enforces this).
- No download button in Phase 2 — result download will be added in Phase 4.
- No WebSocket push — polling is intentional for v1 simplicity.
- No job history list — Phase 5 may add this.
- Single Uvicorn worker (`--workers 1`) — this is intentional, job state is in-memory.

---

<!-- ============================================================ -->
<!-- PHASE 3 ADDITION — Inline Manual Review Form (FRNT-03)       -->
<!-- Added after Phase 2 spec was generated in Lovable.           -->
<!-- Append this section to the existing Lovable project via      -->
<!-- "Edit with Lovable" or by re-pasting to update components.   -->
<!-- ============================================================ -->

## 11. Inline Manual Review Form — Phase 3 Addition (FRNT-03)

This section extends the Job Progress Page (`/jobs/:jobId`) with an inline review form that appears when a job pauses for analyst input. All changes are additive — no existing Phase 2 components need to be removed.

---

### 11.1 Polling Behavior Change

Update the `refetchInterval` in the TanStack Query `useQuery` call on the Job Progress page:

```ts
const { data, queryClient } = useQuery({
  queryKey: ['job-status', jobId],
  queryFn: async () => {
    const res = await apiRequest(`/jobs/${jobId}/status`)
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  refetchInterval: (data) => {
    // Stop polling only on terminal states
    if (data?.status === 'completed' || data?.status === 'failed') return false
    // Keep polling during review_needed — countdown timer needs live data
    // and the job may auto-continue after timeout
    return 2500
  },
})
```

**Key change:** `review_needed` is NOT a terminal state. Polling MUST continue at 2500ms so the countdown timer stays accurate and the UI detects when the job resumes after timeout or submission.

When `data.status === "review_needed"` and `data.review_item` is non-null, render the `ReviewCard` component below the progress section.

---

### 11.2 Updated Status Type

Add `"review_needed"` to the status union and badge color map:

```ts
// Status type (update existing type/enum)
type JobStatus = "queued" | "running" | "review_needed" | "completed" | "failed"

// Status badge color map (update existing StatusBadge component)
const STATUS_BADGE = {
  queued:        { bg: 'bg-gray-200',   text: 'text-gray-700',   label: 'Na fila' },
  running:       { bg: 'bg-blue-100',   text: 'text-blue-700',   label: 'Processando' },
  review_needed: { bg: 'bg-amber-100',  text: 'text-amber-700',  label: 'Aguardando revisao' },
  completed:     { bg: 'bg-green-100',  text: 'text-green-700',  label: 'Concluido' },
  failed:        { bg: 'bg-red-100',    text: 'text-red-700',    label: 'Falhou' },
}
```

---

### 11.3 Progress Bar Behavior During Review

When `data.status === "review_needed"`, update the progress bar display:

- Keep the progress bar at its current `percent` value (do not reset to 0).
- Replace the standard fill animation with a **pulsing/breathing animation** to visually indicate the paused state. Use a CSS `@keyframes` pulse that oscillates the fill color opacity between 100% and 60% on a 1.5s loop (do NOT use an indeterminate shimmer — the position value is known).
- Show text **above** the progress bar: `"Aguardando revisao manual..."` in amber-600, italic.

Example Tailwind class to add to the progress bar fill element when status is `review_needed`:

```
animate-pulse opacity-80
```

---

### 11.4 ReviewCard Component

Add a new `ReviewCard` component. Render it in the Job Progress page **below** the progress section when:

```ts
data?.status === 'review_needed' && data?.review_item != null
```

**Component interface:**

```ts
interface ReviewItem {
  chave_nfse: string
  descricao: string
  municipio: string
  item_lc_original: string
  from_n8n: boolean
  suggested_item_lc: string
  timeout_at: string   // ISO8601 UTC timestamp
}

interface ReviewCardProps {
  jobId: string
  reviewItem: ReviewItem
  onSubmitted: () => void   // called after successful POST to invalidate query cache
}
```

**Layout:** Card style, amber-50 background, amber-200 border, 2px border, rounded-xl, padding 24px. Title: "Revisao Manual Necessaria" in amber-700, bold, 18px, with a warning icon (⚠️) before it.

**Fields (in order):**

1. **Descricao do Servico** (read-only)
   - Label: "Descricao do Servico"
   - Input: `<input type="text" readOnly value={reviewItem.descricao} />`
   - Style: gray-100 background, gray-500 text (visually disabled)

2. **Municipio** (read-only)
   - Label: "Municipio"
   - Input: `<input type="text" readOnly value={reviewItem.municipio} />`
   - Style: gray-100 background, gray-500 text

3. **Sugestao da IA** (read-only hint)
   - No label — render as an inline hint below the Municipio field
   - Text: `"Sugestao IA: {reviewItem.suggested_item_lc}"` in blue-600, small (14px), italic
   - Include a small robot icon (🤖) before the text

4. **Item LC** (required text input)
   - Label: "Item LC (4 digitos)"
   - Input: `<input type="text" maxLength={4} pattern="\d{4}" inputMode="numeric" />`
   - Auto-focused on mount (`autoFocus` attribute)
   - Pre-fill with `reviewItem.suggested_item_lc` as the default value
   - Validation: show inline red error "Item LC deve ter exatamente 4 digitos" if not exactly 4 digits on submit attempt

5. **DDD** (conditional — only render when `reviewItem.from_n8n === false`)
   - Label: "DDD (2 digitos)"
   - Input: `<input type="text" maxLength={2} pattern="\d{2}" inputMode="numeric" />`
   - Required when visible — show inline red error "DDD deve ter exatamente 2 digitos" if not exactly 2 digits on submit attempt
   - Do NOT render this field when `reviewItem.from_n8n === true`

6. **Reference Buttons** (row layout, below the DDD/Item LC inputs):
   - **"Pesquisar Item LC"** button (secondary, outline style):
     ```ts
     window.open(
       `https://www.google.com/search?q=${encodeURIComponent(
         reviewItem.item_lc_original + " - codigo item lc " + reviewItem.municipio + " equivalente goiania"
       )}`,
       "_blank"
     )
     ```
   - **"LC 116"** anchor link (text link style, opens new tab):
     ```html
     <a href="https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm" target="_blank" rel="noopener">
       Lei Complementar 116
     </a>
     ```

7. **Countdown Timer** (rendered above the action buttons):
   - Compute remaining seconds:
     ```ts
     const [remaining, setRemaining] = useState(() =>
       Math.max(0, Math.floor((new Date(reviewItem.timeout_at).getTime() - Date.now()) / 1000))
     )

     useEffect(() => {
       const interval = setInterval(() => {
         setRemaining(prev => Math.max(0, prev - 1))
       }, 1000)
       return () => clearInterval(interval)
     }, [])
     ```
   - Display format: `"Tempo restante: {Math.floor(remaining / 60)}m {remaining % 60}s"` in amber-700, bold
   - When `remaining === 0`: replace with `"Tempo esgotado - aceite automatico"` in red-600, bold

8. **Action Buttons** (row, full width, gap-4):
   - **Confirm button** (primary, orange `#E58A4E`, white text, full-width or flex-1):
     - Text: "Confirmar"
     - Disabled + spinner while POST is in-flight
     - On click:
       ```ts
       const body: Record<string, string> = { item_lc: itemLcValue, action: 'confirm' }
       if (!reviewItem.from_n8n) body.ddd = dddValue
       await apiRequest(`/jobs/${jobId}/review`, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify(body),
       })
       ```
   - **Skip button** (secondary, gray, flex-1):
     - Text: "Pular nota"
     - On click:
       ```ts
       await apiRequest(`/jobs/${jobId}/review`, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ action: 'skip' }),
       })
       ```

---

### 11.5 Post-Submit Behavior

After a successful `POST /jobs/{jobId}/review` (200 response):

1. Call `onSubmitted()` prop — the parent page must invalidate the TanStack Query cache:
   ```ts
   queryClient.invalidateQueries({ queryKey: ['job-status', jobId] })
   ```
2. Do NOT redirect — the progress page stays open and continues showing job progress.
3. The ReviewCard will disappear on next poll once `status` changes away from `"review_needed"`.

**Error handling:**

| HTTP Status | Meaning | UI Action |
|---|---|---|
| 409 | Timeout race — job already auto-continued | Show toast: "Revisao expirada - nota aceita automaticamente" |
| 422 | Validation error (item_lc/ddd wrong length) | Show inline field error (should not reach server, frontend validates first) |
| 403 | Not your job | Show toast: "Acesso negado" |
| 404 | Job not found | Show toast: "Job nao encontrado" |

Use a toast notification (bottom-right, 4s auto-dismiss) for server-side errors.

---

### 11.6 API Contract — POST /jobs/{jobId}/review

```
POST /jobs/{jobId}/review
Authorization: Bearer {supabase_jwt}
Content-Type: application/json

Request body (confirm):
{
  "item_lc": "1401",
  "ddd": "62",
  "action": "confirm"
}

Request body (skip):
{
  "action": "skip"
}

Response 200:
{
  "accepted": true
}

Error responses:
  404 — Job not found
  403 — Not your job (job belongs to a different analyst)
  409 — Job is not waiting for review (already timed out or analyst already submitted)
  422 — Validation error (item_lc not exactly 4 digits, ddd not exactly 2 digits when required)
```

---

### 11.7 Updated GET /jobs/{job_id}/status Response

When `status === "review_needed"`, the poll response includes the `review_item` field:

```json
{
  "job_id": "abc123def456",
  "status": "review_needed",
  "current_note": 12,
  "total_notes": 47,
  "percent": 25.53,
  "recent_logs": ["..."],
  "errors": [],
  "result_ready": false,
  "review_item": {
    "chave_nfse": "001-2026-00013",
    "descricao": "Servicos de consultoria em informatica",
    "municipio": "Goiania",
    "item_lc_original": "1.05",
    "from_n8n": false,
    "suggested_item_lc": "1401",
    "timeout_at": "2026-03-30T20:05:00Z"
  }
}
```

When `status !== "review_needed"`, `review_item` is `null`.

---

### 11.8 Component Checklist — Phase 3 Additions

Add the following components:

- [ ] `ReviewCard` — Inline review form with all fields, countdown timer, confirm/skip actions
- [ ] `CountdownTimer` — Self-contained hook/component that decrements every second from `timeout_at`

Update the following existing components:

- [ ] `JobProgress` — Add `ReviewCard` rendering when `status === "review_needed"`, update polling `refetchInterval` to not stop on `review_needed`, add pulsing progress bar state, add `"Aguardando revisao manual..."` text
- [ ] `StatusBadge` — Add `review_needed` → amber badge mapping

---

<!-- ============================================================ -->
<!-- PHASE 4 ADDITION — Results and Download Section (FRNT-04)    -->
<!-- Added after Phase 3 spec was generated in Lovable.           -->
<!-- Append this section to the existing Lovable project via      -->
<!-- "Edit with Lovable" or by re-pasting to update components.   -->
<!-- ============================================================ -->

## 12. Results and Download Section — Phase 4 Addition (FRNT-04)

This section extends the Job Progress Page (`/jobs/:jobId`) with a results summary and download buttons that appear when the job completes. All changes are additive — no existing Phase 2 or Phase 3 components need to be removed.

The same progress page transitions to a "completed" state. No navigation to a separate results page occurs — the analyst stays on the same `/jobs/:jobId` route.

---

### 12.1 State Transition: Progress → Results

Update the polling logic in `JobProgress` so that when `result_ready` becomes `true`, the component fetches the file metadata once and renders `ResultsSection` below the progress area.

```ts
const { data: statusData } = useQuery({
  queryKey: ['job-status', jobId],
  queryFn: async () => {
    const res = await apiRequest(`/jobs/${jobId}/status`)
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  refetchInterval: (data) => {
    if (data?.status === 'completed' || data?.status === 'failed') return false
    return 2500
  },
})

// Fetch file metadata once when result_ready=true
const { data: filesData } = useQuery({
  queryKey: ['job-files', jobId],
  queryFn: async () => {
    const res = await apiRequest(`/jobs/${jobId}/files`)
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  enabled: statusData?.result_ready === true,
  staleTime: Infinity,  // don't refetch — file list is stable for a completed job
})
```

When `statusData?.result_ready === true` and `filesData` is available, render `ResultsSection` below the existing progress indicators (status badge, progress bar, log stream).

---

### 12.2 ResultsSection Component

**Component:** `ResultsSection`

**Props:**

```ts
interface FilesData {
  job_id: string
  emp_cod: string
  vigencia: string
  summary: {
    total: number
    errors: number
    skipped: number
    processing_seconds: number | null
  }
  files: Array<{
    type: 'txt' | 'csv' | 'txt_split'
    label: string
    url: string
    vigencia?: string
  }>
}

interface ResultsSectionProps {
  jobId: string
  filesData: FilesData
  onNewJob: () => void  // called when analyst clicks "Start New Job"
}
```

**Data source:** `GET /jobs/{id}/files` returns `FilesData` with summary and file list (fetched once in step 12.1).

---

### 12.3 Summary Card

Render a summary card at the top of `ResultsSection`:

```
"Processadas {total} notas em {processing_seconds}s — {errors} erros, {skipped} ignoradas"
```

- If `processing_seconds` is null, omit the time phrase: `"Processadas {total} notas — {errors} erros, {skipped} ignoradas"`
- If `errors > 0`: render the errors count in **destructive red** (`text-red-600` or the Error color token `#C0392B`)
- If `errors === 0`: render the full summary in success green (`text-green-700`)
- Card style: `bg-green-50 border border-green-200 rounded-xl p-4` (or `bg-red-50 border border-red-200` when `errors > 0`)

---

### 12.4 Download Buttons

Below the summary card, render a download buttons section:

**Layout:** Vertical stack with 12px gap. Section title: "Downloads" in bold, 16px, gray-700.

**Main TXT file** (always present — `files.find(f => f.type === 'txt')`):

```tsx
<a
  href={`${import.meta.env.VITE_API_URL}${file.url}`}
  download={file.label}
  className="btn-primary w-full"  // blue primary button, full width
>
  Baixar TXT — {file.label}
</a>
```

Style: primary button (use the primary color token — blue `#3498DB` works here as a download action, distinct from the orange submit button).

**CSV report** (always present — `files.find(f => f.type === 'csv')`):

```tsx
<a
  href={`${import.meta.env.VITE_API_URL}${file.url}`}
  download={file.label}
  className="btn-outline w-full"  // outline/secondary button
>
  Baixar CSV — {file.label}
</a>
```

Style: outline/secondary button (bordered, transparent background).

**Split TXT files** (conditional — `files.filter(f => f.type === 'txt_split')`):

Only render this subsection if there is at least one `txt_split` entry.

```tsx
{splitFiles.length > 0 && (
  <div>
    <p className="text-sm font-medium text-gray-600 mb-2">Arquivos por vigencia diferente:</p>
    {splitFiles.map(file => (
      <a
        key={file.vigencia}
        href={`${import.meta.env.VITE_API_URL}${file.url}`}
        download={file.label}
        className="btn-outline w-full mb-2"
      >
        Baixar TXT — {file.label}
      </a>
    ))}
  </div>
)}
```

**Download behavior:** All download buttons use `<a href=... download=...>`. The browser triggers a file download using the `Content-Disposition: attachment` header returned by the API. No custom fetch logic needed.

**Auth note:** Download links must include the JWT. Since `<a href>` does not send custom headers, use one of these approaches:
- Option A (recommended): Generate a short-lived pre-authenticated URL on the backend (out of scope for now — use Option B for v1).
- Option B (v1): Intercept click → `fetch()` with `Authorization` header → `URL.createObjectURL()` → programmatic click on a temporary `<a>` element → `URL.revokeObjectURL()`.

```ts
async function downloadWithAuth(url: string, filename: string) {
  const res = await apiRequest(url)
  if (!res.ok) throw new Error(`Download failed: ${res.status}`)
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(objectUrl)
}
```

Replace all `<a href=...>` download anchors with `<button onClick={() => downloadWithAuth(file.url, file.label)}>` for correct auth handling.

---

### 12.5 "Start New Job" Button

Below all download buttons:

```tsx
<button
  onClick={onNewJob}
  className="w-full mt-4 btn-secondary"
>
  Novo Job
</button>
```

**`onNewJob` callback behavior (implement in parent `JobProgress`):**

1. Clear the current `jobId` from component state.
2. Navigate to `/upload` using React Router: `navigate('/upload')`.

This resets the page to the upload form so the analyst can start a new submission immediately.

---

### 12.6 Updated Section 6.7 — Completed Terminal State

Replace the existing Phase 2 placeholder in Section 6.7 ("On completed") with:

```
Green checkmark icon + "Processamento concluido com sucesso!"
Subtitle: "X notas processadas."
[ResultsSection renders below — see Section 12]
```

Remove the placeholder comment `(Phase 4 will add download buttons here)`.

---

### 12.7 API Contract — GET /jobs/{id}/files

```
GET /jobs/{jobId}/files
Authorization: Bearer {supabase_jwt}

Response 200:
{
  "job_id": "abc123def456",
  "emp_cod": "001",
  "vigencia": "03/2026",
  "summary": {
    "total": 47,
    "errors": 2,
    "skipped": 0,
    "processing_seconds": 14.3
  },
  "files": [
    { "type": "txt",       "label": "001_032026.txt",          "url": "/jobs/abc123def456/download/txt",          "vigencia": "" },
    { "type": "csv",       "label": "relatorio_001_032026.csv", "url": "/jobs/abc123def456/download/csv",          "vigencia": "" },
    { "type": "txt_split", "label": "001_022026.txt",           "url": "/jobs/abc123def456/download/txt/022026",   "vigencia": "022026" }
  ]
}

Error responses:
  403 — Not your job
  404 — Job not found or result unavailable
  409 — Job is not yet completed
```

---

### 12.8 Component Checklist — Phase 4 Additions

Add the following components:

- [ ] `ResultsSection` — Summary card + download buttons + "Start New Job" action
- [ ] `DownloadButton` — Reusable button that performs authenticated fetch → blob → programmatic download

Update the following existing components:

- [ ] `JobProgress` — Add `filesData` query (enabled when `result_ready=true`), render `ResultsSection` when completed, wire `onNewJob` to navigate('/upload')
- [ ] Section 6.7 completed state — replace placeholder comment with `ResultsSection` reference
