# SahayakAI

SahayakAI is a hackathon project we're building to make web forms and public-service websites easier to use, especially for people who prefer Hindi or have difficulty navigating websites.

The idea is simple: users should be able to explain what they need in Hindi or English, review the information before the assistant enters it, and approve an action before anything is submitted. The assistant should also be able to stop when asked and report what actually happened.

## What we're building

The prototype has two planned workflows:

- **myScheme discovery:** Help users find potentially relevant government schemes using information from the official website. This workflow will be read-only and will never submit an application to a real government website.
- **Demo application form:** Use a separate test website with fake information to demonstrate filling out a form and submitting it only after the user gives explicit approval.

The myScheme workflow will be included in the demo only if it proves reliable during testing. Otherwise, we'll focus on the demo form.

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
validates the JSON response before any task can reach approval.

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
python -m unittest backend.tests.test_api backend.tests.test_tinyfish_agent backend.tests.test_planner backend.tests.test_m5_verification backend.tests.test_m6_planner mock_site.tests.test_store mock_site.tests.test_app -v
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

## Team responsibilities

- **Owner A:** Backend, TinyFish integration, orchestration, planning, and verification.
- **Owner B:** Frontend, voice interaction, accessibility, and demo presentation.

We'll build the application in small milestones and test each part before integrating it.

## Safety rules

- Use fake information in the demo.
- Ask for approval before consequential actions.
- Never submit an application on a real government website.
- Stop at CAPTCHA, OTP, or login requirements rather than trying to bypass them.
- Don't report success unless the available evidence supports it.

More details about the architecture, API contract, and implementation requirements are maintained in `SPEC.md`.
