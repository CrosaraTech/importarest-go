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
