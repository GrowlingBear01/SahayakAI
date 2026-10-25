import json

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .flow_loader import load_flows
from .orchestrator import orchestrator
from .schemas import (
    AnswerRequest,
    ApproveRequest,
    CreateTaskRequest,
    FlowType,
    TaskState,
)


app = FastAPI(title="SahayakAI")


def configure_cors(application: FastAPI, allowed_origins: tuple[str, ...]) -> None:
    if "*" in allowed_origins:
        raise ValueError("CORS_ALLOWED_ORIGINS must list exact trusted origins")
    if allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )


configure_cors(app, settings.cors_allowed_origins)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/ready")
async def readiness(response: Response) -> dict[str, object]:
    checks = {
        "llm_provider": settings.llm_provider == "gemini",
        "llm_api_key": bool(settings.llm_api_key),
        "tinyfish_api_key": (
            settings.browser_agent != "tinyfish" or bool(settings.tinyfish_api_key)
        ),
    }
    ready = all(checks.values())
    if not ready:
        response.status_code = 503
    return {"ok": ready, "checks": checks}


@app.post("/tasks")
async def create_task(request: CreateTaskRequest) -> dict[str, str]:
    task = await orchestrator.create_task(
        request.text,
        request.lang,
        request.flow,
        request.history,
    )
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
    try:
        await orchestrator.answer(task_id, request.text)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="task not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
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
    flow = orchestrator.flows.get(task.flow_id) if task.flow_id else None
    is_discovery = flow is not None and flow.flow_type == FlowType.DISCOVERY
    is_myscheme = flow is not None and flow.id == "myscheme_discovery"
    if task.state == TaskState.SUBMITTING:
        note_en = (
            "Stop requested during submission. The backend is checking whether "
            "the demo site accepted it."
        )
        note_hi = "जमा करते समय रोकने का अनुरोध मिला। डेमो साइट पर स्थिति जाँची जा रही है।"
    elif task.state == TaskState.DONE:
        if is_discovery:
            note_en = (
                "The read-only myScheme search is already complete."
                if is_myscheme
                else "The read-only website search is already complete."
            )
            note_hi = (
                "myScheme पर केवल पढ़कर खोज पूरी हो चुकी है।"
                if is_myscheme
                else "वेबसाइट पर केवल पढ़कर खोज पूरी हो चुकी है।"
            )
        else:
            note_en = "The demo submission was already verified."
            note_hi = "डेमो जमा होने की पुष्टि पहले ही हो चुकी है।"
    elif task.state == TaskState.OUTCOME_UNKNOWN:
        if is_discovery:
            note_en = (
                "myScheme results could not be confirmed. No application was submitted."
                if is_myscheme
                else "The website result could not be confirmed. No form was submitted."
            )
            note_hi = (
                "myScheme के परिणामों की पुष्टि नहीं हो सकी। कोई आवेदन जमा नहीं हुआ।"
                if is_myscheme
                else "वेबसाइट के परिणाम की पुष्टि नहीं हो सकी। कोई फ़ॉर्म जमा नहीं हुआ।"
            )
        else:
            note_en = (
                "The submission outcome is unknown. Check the demo site before "
                "taking any further action; do not retry automatically."
            )
            note_hi = (
                "जमा होने की स्थिति अज्ञात है। आगे कुछ करने से पहले डेमो साइट जाँचें; "
                "अपने-आप दोबारा न भेजें।"
            )
    else:
        note_en = "Stopped. Actions already taken may remain."
        note_hi = "रोक दिया गया। पहले किए गए काम का असर रह सकता है।"
    return {
        "ok": True,
        "state": task.state.value,
        "evidence": task.evidence,
        "reason": task.reason,
        "needs_human_kind": task.needs_human_kind,
        "human_action_url": task.human_action_url,
        "flow_id": task.flow_id,
        "schemes": [scheme.model_dump() for scheme in task.schemes],
        "web_answer": task.web_answer,
        "web_sources": [source.model_dump() for source in task.web_sources],
        "web_media": [media.model_dump() for media in task.web_media],
        "web_media": [media.model_dump() for media in task.web_media],
        "selected_site": next(
            (
                candidate.model_dump()
                for candidate in task.web_candidates
                if candidate.url == task.selected_site_url
            ),
            None,
        ),
        "offer_demo": (
            is_myscheme
            and task.state
            in {TaskState.COULD_NOT_FINISH, TaskState.OUTCOME_UNKNOWN}
        ),
        "summary_en": task.error or note_en,
        "summary_hi": task.error_hi or note_hi,
        "note_key": (
            "stop_too_late"
            if task.state == TaskState.DONE and task.cancelled
            else None
        ),
        "note": note_en,
        "note_en": note_en,
        "note_hi": note_hi,
    }


@app.get("/flows")
async def get_flows():
    return [
        {"id": flow.id, "title_en": flow.title_en, "title_hi": flow.title_hi}
        for flow in load_flows().values()
    ]
