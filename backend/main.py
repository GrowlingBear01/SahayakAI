import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .flow_loader import load_flows
from .orchestrator import orchestrator
from .schemas import AnswerRequest, ApproveRequest, CreateTaskRequest, TaskState


app = FastAPI(title="SahayakAI")


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/tasks")
async def create_task(request: CreateTaskRequest) -> dict[str, str]:
    task = await orchestrator.create_task(request.text, request.lang)
    return {"task_id": task.task_id}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = orchestrator.store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.get("/tasks/{task_id}/events")
async def task_events(task_id: str) -> StreamingResponse:
    if orchestrator.store.get(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    event_stream = orchestrator.events(task_id)

    async def stream():
        async for event in event_stream:
            yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/tasks/{task_id}/answer")
async def answer_task(task_id: str, request: AnswerRequest) -> dict[str, bool]:
    if orchestrator.store.get(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True}


@app.post("/tasks/{task_id}/approve")
async def approve_task(
    task_id: str, request: ApproveRequest
) -> dict[str, bool]:
    try:
        await orchestrator.approve(task_id, request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="task not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"ok": True}


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, bool]:
    try:
        task = await orchestrator.stop(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="task not found") from error
    return {"ok": True}


@app.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str) -> dict[str, object]:
    try:
        task = await orchestrator.stop(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="task not found") from error
    return {
        "ok": True,
        "state": task.state.value,
        "note": "Stopped. Actions already taken may remain.",
    }


@app.get("/flows")
async def get_flows():
    return [
        {"id": flow.id, "title_en": flow.title_en, "title_hi": flow.title_hi}
        for flow in load_flows().values()
    ]
