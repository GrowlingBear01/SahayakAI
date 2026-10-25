# SahayakAI

SahayakAI is a voice-and-text assistant. People can speak or type naturally,
receive a conversational response, and continue with follow-up turns. When a
request matches an available tool, SahayakAI can help carry it out with clear
review and approval before consequential actions.

The product goal is broader than any single website or domain. Government
schemes and forms are examples, not the product boundary. The current prototype
is an early step toward that goal, not a general-purpose agent that can safely
perform every task.

## What we're building

The prototype currently supports:

- **Conversation:** General questions, explanations, drafting, brainstorming, and follow-up turns in Hindi or English. The latest 12 conversation messages are sent to Gemini as context; starting a new conversation clears the in-memory chat history.
- **Any public website:** In “Any public website” mode, provide the exact public HTTPS address and what you want to find. TinyFish reads public pages only after you approve the request, then returns an answer with same-site source links. The address is user-provided and SahayakAI does not independently verify site ownership. Natural-language website searches in Assistant mode may use Gemini's Google Search grounding to find likely official sites. Login, CAPTCHA, OTP, form filling, and submissions are out of scope.
- **Demo application form:** Use a separate test website with fake information to demonstrate filling out a form and submitting it only after the user gives explicit approval.
- **myScheme discovery:** A guarded, read-only search of public myScheme pages. It does not enter personal details, submit applications, or confirm eligibility.

## Current status

The repository contains a bilingual conversation-and-action prototype. The current browser
agent defaults to a deterministic mock adapter; live TinyFish integration is
available as a separate adapter and must be configured explicitly.

**Implemented**
- FastAPI task, approval, stop, flow, and replayable SSE endpoints.
- React/Vite interface with typed requests, approval review/edit controls,
  progress, voice controls, and task results.
- Gemini planner using schema-constrained JSON, a needs-information answer loop,
  bounded recent-turn context, conversational responses, and server-side
  validation against the selected flow's declared fields.
- Separate SQLite-backed demo form with expiring, revocable, single-use
  submission codes and payload binding.
- Server-authoritative success verification: the backend reports a successful
  submission only when the demo site's SQLite record matches the task, approved
  payload, and one-time code.
- Conservative handling for uncertain submission outcomes; the application
  does not automatically retry a submission without verified status.
- TinyFish adapter with polling, cancellation handling, screenshots, and live
  browser-view URL support.
- Generic read-only website discovery: explicit website mode accepts a
  user-provided public HTTPS address without depending on Gemini Search;
  Assistant-mode named-site search can use Gemini's Google Search grounding.
  Both paths require approval, use same-host source filtering, and return an
  answer backed by public page links. The deterministic mock agent does not
  simulate or browse arbitrary websites.
- Public music/video discovery: searches YouTube for user-requested titles,
  artists, or topics, and returns validated public video links. A user-provided
  YouTube share link is normalized to its canonical video URL. Browsing requires
  explicit approval, and users choose whether to open or play media; the agent
  does not click, play, sign in, or perform other site actions. Explicit YouTube
  search commands use the known public YouTube domain directly instead of
  waiting on the general-purpose request planner.
- myScheme discovery with a separate pre-run approval, page-sourced scheme
  descriptions, optional Hindi translations when returned, same-site-only links,
  and a demo-form fallback when results cannot be safely extracted.

**Not yet implemented**
- Arbitrary task execution or integrations for email, calendars, messaging,
  files, music playback, purchases, or other external services. The assistant
  must be honest about these limits; adding them requires dedicated integrations,
  user authorization, scoped credentials, and action-specific confirmation.
- Durable conversation history, user accounts, or cross-device memory. The
  current conversation context lives only in frontend memory and is limited to
  the latest 12 messages.
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

The request, up to 12 recent conversation messages, and any values collected
for a task are sent to Gemini. Do not include sensitive personal information.

### 1. Start the backend

From the repository root, run these commands in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --reload --env-file .env
```

The planner uses `LLM_PROVIDER=gemini` and `LLM_MODEL=gemini-3.8-flash` by
default. On a Gemini 503 response or read timeout, generation retries once with
`gemini-3.5-flash-lite`; quota errors are not retried with another model. The
planner validates the JSON response before any task can reach approval.
Conversation history is held only in frontend memory and is cleared with
**New conversation**. Explicit public-website mode uses the exact HTTPS address
provided by the user and does not require Gemini Search grounding.

The browser agent defaults to `BROWSER_AGENT=mock` for offline development.
To run tasks with TinyFish, set `BROWSER_AGENT=tinyfish` and configure
`TINYFISH_API_KEY` in `.env`. For the demo form, TinyFish must be able to reach
the demo site over public HTTPS, so set `MOCK_SITE_BASE_URL` to the HTTPS tunnel
URL for the separate mock-site app. Keep both processes on the same machine
because they share the mock site's local SQLite verification database. Generic
website discovery also requires `BROWSER_AGENT=tinyfish`; the mock agent does
not simulate or browse arbitrary sites. The myScheme read-only search also
requires TinyFish; selecting it with the mock agent now reports the required
configuration instead of starting a browser task that cannot succeed. When
TinyFish is selected, a missing API key is a startup error; the backend will
not silently fall back to the mock agent.

The backend API docs and health endpoint are available at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/flows`

`/health` is a liveness check. `/ready` checks local planner/provider
configuration and returns HTTP 503 when required configuration is missing; it
does not make external API calls. For cross-origin frontend deployments, set
`CORS_ALLOWED_ORIGINS` to a comma-separated list of exact trusted origins. The
default is same-origin only.

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
npm run lint
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

## Deployment limitations

This is a local prototype, not a public multi-user service. Task IDs currently
do not enforce user ownership, task/event state is in memory, and the API has no
authentication, per-user rate limits, or concurrency quotas. Keep the backend
bound to localhost and do not expose it publicly until those controls and
shared durable task storage are implemented. The readiness endpoint is a
configuration check, not a security or dependency-availability guarantee.
