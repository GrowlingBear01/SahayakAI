# SahayakAI frontend (Owner B)

Voice-first React + Vite client for SahayakAI. It talks to Owner A’s backend using the documented REST and SSE contract. It does not store transcripts, form values, or task history in browser storage.

## Run

From `frontend/`:

```powershell
npm install
npm run dev
```

Then open the URL Vite prints (usually `http://localhost:5173`).

Copy `.env.example` to `.env` if you need to point at a specific API origin:

```
VITE_API_BASE_URL=
```

With no `VITE_API_BASE_URL`, the frontend uses same-origin API requests. Local
`npm run dev` proxies `/health`, `/flows`, and `/tasks` to
`VITE_BACKEND_URL` (default `http://localhost:8000`) so EventSource runs
same-origin. For a separately hosted frontend, set `VITE_API_BASE_URL` to the
backend's HTTPS origin during the production build; production builds do not
fall back to the visitor's `localhost`.

Start Owner A’s API separately (from the repository root):

```powershell
python -m uvicorn backend.main:app --reload
```

This frontend branch may only have `/health` until Owner A’s task API is running. The UI stays usable and reports that honestly.

## Checks

```powershell
npm test
npm run build
```

`npm run lint` runs ESLint independently of the production build.

## Voice

- Push-to-talk with the Web Speech API (`hi-IN`, `en-IN`).
- Typed input is always available.
- Auto language picks Hindi or English from the **browser language**. It does not claim mixed-language recognition.
- Only Hindi and English are supported.
- Stopping speech is not the same as STOP on a cloud-browser task.

## Safety

- Create-task sends only `{ text, lang }`.
- Start approval and submit approval are separate screens driven by backend `approval_type`.
- Edits send a new review; stale `approval_id` values are not reused after a 409.
- Results render `done`, `could_not_finish`, `stopped`, and `outcome_unknown` from the backend. Evidence kinds are shown as returned. No reference numbers are invented.
- A demo-form proposal while Real Website is selected is surfaced; the flow badge is not silently switched.
