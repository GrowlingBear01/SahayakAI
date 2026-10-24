from fastapi import FastAPI


app = FastAPI(title="SahayakAI")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

