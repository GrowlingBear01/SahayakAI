# SahayakAI

SahayakAI is a hackathon project we're building to make web forms and public-service websites easier to use, especially for people who prefer Hindi or have difficulty navigating websites.

The idea is simple: users should be able to explain what they need in Hindi or English, review the information before the assistant enters it, and approve an action before anything is submitted. The assistant should also be able to stop when asked and report what actually happened.

## What we're building

The prototype has two planned workflows:

- **myScheme discovery:** Help users find potentially relevant government schemes using information from the official website. This workflow will be read-only and will never submit an application to a real government website.
- **Demo application form:** Use a separate test website with fake information to demonstrate filling out a form and submitting it only after the user gives explicit approval.

The myScheme workflow will be included in the demo only if it proves reliable during testing. Otherwise, we'll focus on the demo form.

## Current status

This repository is at the initial application-scaffold stage.

**Implemented so far**
- A basic FastAPI backend with a health endpoint.
- A React application using Vite.
- Initial dependency definitions and an environment-variable template.

**Still to be implemented**
- TinyFish browser automation.
- The demo website and its submission verification.
- Task planning and orchestration.
- Approval controls, progress updates, and STOP handling.
- Hindi and English voice interaction.

This list will be updated as the features are implemented and tested.

## Tech stack

- **Frontend:** React and Vite
- **Backend:** Python and FastAPI
- **Browser automation:** TinyFish Agent API
- **Validation:** Pydantic
- **Demo submission records:** SQLite

## Run locally

You'll need Python, Node.js, and npm installed.

### 1. Start the backend

From the repository root, run these commands in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload
```

The initial health endpoint is available at:

`http://127.0.0.1:8000/health`

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
python -m unittest backend.tests.test_api mock_site.tests.test_store -v
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
