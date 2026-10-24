# SahayakAI

> **Capable enough to help. Honest enough to trust.**

SahayakAI is a voice-first assistant designed to help Hindi-first, low-digital-literacy
users complete web tasks without giving up control. It explains what it will do,
asks for approval before acting, stops when asked, and never claims success without
evidence.

## Why this matters

Government and public-service websites can be difficult to navigate even when the
user knows exactly what they need. SahayakAI is designed around a simple promise:

> A user should not have to choose between getting help and staying in control.

The product is built for a persona like **Savitri, 72**, who can describe her need
in Hindi but may find forms, unfamiliar terminology, and multi-step websites
challenging.

## What the hackathon demo will show

The demo has two deliberately separated flows:

1. **myScheme discovery** — a read-only search for possible government schemes,
   using only information shown on the official site. It never submits an
   application on a real website.
2. **Demo form submission** — a clearly labelled fake form where TinyFish fills
   invented user details. Submission requires a second, explicit approval and is
   accepted only when the demo server verifies its own submission record.

The primary interaction is voice-first Hindi (`hi-IN`) with English (`en-IN`) and
typed input always available as a fallback.

## Trust and safety by design

- **Approval before action:** the user sees the exact details and destination
  before anything is sent to the cloud browser or typed into a site.
- **Two approval boundaries:** filling a submission form and submitting it are
  separate actions requiring separate approvals.
- **STOP is always available:** stopping a task sets a cancellation flag and
  requests cancellation from the browser agent. In-flight outcomes are reported
  honestly.
- **Evidence-based results:** a completed browser run is not treated as proof of
  success. Demo submissions are verified against the server's record.
- **No bypassing:** CAPTCHA, OTP, login, or unexpected sensitive-data requests
  result in a human handoff. SahayakAI never attempts to bypass them.
- **Fake data only:** the demo uses invented names, ages, and phone numbers.
  Secrets are read from environment variables and are never committed.
- **Restricted boundaries:** the planner cannot provide arbitrary URLs or browser
  goals; flows and fields are validated by the backend.

## Architecture

```text
React + Vite UI
  |  REST actions + Server-Sent Events
  v
FastAPI backend
  Planner -> Orchestrator state machine -> Verifier
                    |
                    v
             BrowserAgent adapter
                    |
                    v
             TinyFish cloud browser
              /                 \
       myScheme (read-only)   public demo form
```

The orchestrator owns task state and emits an event for every transition. The
planned state machine includes `planning`, `needs_info`, `working`,
`waiting_for_approval`, `submitting`, `done`, `could_not_finish`, `stopped`, and
`outcome_unknown`.

## Current repository status

The repository currently contains the initial application scaffold:

- FastAPI backend with a health endpoint
- React/Vite frontend shell
- Environment-variable template
- Dependency manifests with pinned initial versions
- Repository safety defaults in `.gitignore`

The remaining demo milestones are being built incrementally: flow schemas and
task state, the mock browser agent, orchestration and SSE, the TinyFish adapter,
server-authoritative demo verification, planner validation, voice interaction,
and failure-path hardening.

## Project structure

```text
.
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── requirements.txt     # Backend dependencies
│   └── __init__.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Frontend entry screen
│   │   └── main.jsx         # React bootstrap
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── .env.example             # Configuration template; no secrets
└── README.md
```

## Run locally

### Backend

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload
```

The initial health check is available at
`http://127.0.0.1:8000/health`.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env` when configuring local development. Never commit
`.env` or any API key.

## Team ownership

- **Owner A:** backend, TinyFish integration, planner, orchestrator, verifier, and
  safety boundaries.
- **Owner B:** frontend, voice interaction, accessibility, demo assets, and pitch.

The work is organized as small, reviewable milestones so `main` remains
demo-ready throughout the hackathon.

## Roadmap beyond the hackathon

The current scope intentionally does not include accounts, persistent profiles,
general "any website" automation, mobile apps, payments, hands-free wake-word
operation, audit history, or real submissions on real government sites. These are
future roadmap items, not hidden demo capabilities.
