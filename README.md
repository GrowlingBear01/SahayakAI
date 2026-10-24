# SahayakAI

## Project structure

- `backend/` contains the FastAPI application.
- `frontend/` contains the React and Vite application.
- `.env.example` lists the configuration values used by local development.

## Local development

Start the backend:

```powershell
python -m uvicorn backend.main:app --reload
```

Install frontend dependencies and start Vite:

```powershell
cd frontend
npm install
npm run dev
```
