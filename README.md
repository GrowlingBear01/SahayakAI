# SahayakAI

SahayakAI is a hackathon project we're building to make web forms and public-service websites easier to use, especially for people who prefer Hindi or have difficulty navigating websites.

The idea is simple: users should be able to explain what they need in Hindi or English, review the information before the assistant enters it, and approve an action before anything is submitted. The assistant should also be able to stop when asked and report what actually happened.

## What we're building

The prototype has three workflows:

- **myScheme discovery:** A guarded, read-only search of public myScheme pages. It does not enter personal details, submit applications, or confirm eligibility. The M0 smoke test had one successful English run; repeat and Hindi runs timed out, so treat this as optional and do not rely on it for the stage demo.
- **Any public website:** Choose “Any public website” and enter a site or service name. Gemini's Google Search grounding API finds likely official sites without opening a search-results page in TinyFish. A single high-confidence match is shown before the app asks what to look up; ambiguous matches require the user to choose. TinyFish then reads public pages on that hostname and returns an answer with same-site source links. This is best-effort, not coverage of every website or independent verification of a site's ownership. Login, CAPTCHA, OTP, form filling, and submissions are out of scope.
- **Demo application form:** Use a separate test website with fake information to demonstrate filling out a form and submitting it only after the user gives explicit approval.

## Current status

The repository contains an end-to-end bilingual demo flow. The current browser
agent defaults to a deterministic mock adapter; live TinyFish integration is
available as a separate adapter and must be configured explicitly.

**Implemented**
- FastAPI task, approval, stop, flow, and replayable SSE endpoints.
- React/Vite interface with typed requests, approval review/edit controls,
  progress, voice controls, and task results.
- Gemini planner using schema-constrained JSON, a needs-information answer loop,
  and server-side validation against the selected flow's declared fields.
- Separate SQLite-backed demo form with expiring, revocable, single-use
  submission codes and payload binding.
- Server-authoritative success verification: the backend reports a successful
  submission only when the demo site's SQLite record matches the task, approved
  payload, and one-time code.
- Conservative handling for uncertain submission outcomes; the application
  does not automatically retry a submission without verified status.
- TinyFish adapter with polling, cancellation handling, screenshots, and live
  browser-view URL support.
- Generic read-only website discovery: site-name search using Gemini's Google
  Search grounding API, candidate selection when ambiguous, same-host source
  filtering, and an answer backed by public page links. TinyFish browses the
  selected site only; the deterministic mock agent does not simulate or browse
  arbitrary websites.
- myScheme discovery with a separate pre-run approval, page-sourced scheme
  descriptions, optional Hindi translations when returned, same-site-only links,
  and a demo-form fallback when results cannot be safely extracted.

**Not yet implemented**
- Production-grade planner and deployments with a configured Gemini API key.
- Real government website submission. This is intentionally out of scope; only
  the clearly labelled fake demo form may be submitted.
- Production database-backed task persistence and deployment hardening.

## Tech stack

- **Frontend:** React and Vite
- **Backend:** Python and FastAPI
- **Browser automation:** TinyFish Agent API
- **Validation:** Pydantic
- **Demo submission records:** SQLite

## Run locally

You'll need Python, Node.js, and npm installed.

Before starting the backend, copy `.env.example` to `.env` and set
`LLM_API_KEY` to your Gemini API key. The key stays on the backend and must not
be committed or pasted into chat.

### 1. Start the backend

From the repository root, run these commands in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload --env-file .env
```

The planner uses `LLM_PROVIDER=gemini` and `LLM_MODEL=gemini-3.8-flash` by
default. It sends requests through Gemini's stateless Interactions API and
validates the JSON response before any task can reach approval. Public website
discovery also uses Gemini's Google Search grounding tool with the same API key;
it no longer opens a Google results page in TinyFish.

The browser agent defaults to `BROWSER_AGENT=mock` for offline development.
To run tasks with TinyFish, set `BROWSER_AGENT=tinyfish` and configure
`TINYFISH_API_KEY` in `.env`. For the demo form, TinyFish must be able to reach
the demo site over public HTTPS, so set `MOCK_SITE_BASE_URL` to the HTTPS tunnel
URL for the separate mock-site app. Keep both processes on the same machine
because they share the mock site's local SQLite verification database. Generic
website discovery also requires `BROWSER_AGENT=tinyfish`; the mock agent does
not simulate or browse arbitrary sites. When TinyFish is selected, a missing
API key is a startup error; the backend will not silently fall back to the mock
agent.

The backend API docs and health endpoint are available at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/flows`

### 2. Start the separate demo site

Open another terminal from the repository root:

```powershell
python -m uvicorn mock_site.app:app --host 127.0.0.1 --port 8001
```

The demo form is available at `http://127.0.0.1:8001/mock/form`.

### 3. Start the frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Vite will print the local address for the frontend.

Run the backend and mock-site tests from the repository root:

```powershell
python -m unittest discover -s backend/tests -v
python -m unittest discover -s mock_site/tests -v
```

Run frontend tests and a production build from `frontend`:

```powershell
npm ci
npm test
npm run build
```

### 4. Configure environment variables

Copy `.env.example` to `.env` when needed and add your local configuration. Keep API keys in `.env`; never commit secrets to GitHub.

The TinyFish smoke test will also require a valid API key and a public HTTPS URL for the demo website.

### M10 live hardening run

After starting the separate mock-site app and its public HTTPS tunnel, run this
from the repository root:

```powershell
python scripts\measure_m10.py
```

This performs up to 20 sequential TinyFish demo cycles using invented data.
Each cycle requires separate start and submit approvals in the orchestrator and
creates a fake demo submission. The script checks the TinyFish wallet (at least
an estimated USD $10 budget) and the public demo form before it starts. It
updates `reports\m10_metrics.json` after every cycle with the pass/fail
denominator and latency; no API keys, references, or form values are recorded.
Live TinyFish calls incur usage costs. The backup video must be recorded
separately and is not produced by this script.

## Team responsibilities

- **Owner A:** Backend, TinyFish integration, orchestration, planning, and verification.
- **Owner B:** Frontend, voice interaction, accessibility, and demo presentation.

We'll build the application in small milestones and test each part before integrating it.

## Safety rules

- Use fake information in the demo.
- Ask for approval before consequential actions.
- Never submit an application on a real government website.
- Stop at CAPTCHA, OTP, or login requirements rather than trying to bypass them.
  When available, the app links to the site so the user can continue manually;
  completing a challenge in that separate tab does not resume the cloud run.
- Don't report success unless the available evidence supports it.

More details about the architecture, API contract, and implementation requirements are maintained in `SPEC.md`.
