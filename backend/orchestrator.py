import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

from .agents.base import BrowserAgent
from .agents.mock_agent import MockBrowserAgent
from .flow_loader import load_flows
from .schemas import ApproveRequest, Task, TaskEvent, TaskState
from .task_store import TaskStore


DEMO_VALUES = {
    "full_name": "Savitri Devi",
    "age": 72,
    "state": "Delhi",
    "phone": "9876543210",
}


class Orchestrator:
    def __init__(
        self, store: TaskStore, agent: BrowserAgent | None = None
    ) -> None:
        self.store = store
        self.agent = agent or MockBrowserAgent()
        self.flows = load_flows()
        self._listeners: dict[str, list[asyncio.Queue[TaskEvent | None]]] = {}
        self._history: dict[str, list[TaskEvent]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, text: str, language: str) -> Task:
        task = Task(
            task_id=str(uuid4()),
            flow_id="mock_scheme_application",
            values=DEMO_VALUES,
            text=text,
            language=language,
        )
        self.store.create(task)
        await self._emit(
            task,
            "Preparing the demo form.",
            "डेमो फ़ॉर्म तैयार कर रहा हूँ।",
            1,
            4,
        )
        task.approval_id = str(uuid4())
        task.approval_type = "start"
        task.state = TaskState.WAITING_FOR_APPROVAL
        self.store.replace(task)
        await self._emit(
            task,
            "Please approve starting the demo form.",
            "डेमो फ़ॉर्म शुरू करने की अनुमति दें।",
            2,
            4,
            self._approval_data(task, "start"),
        )
        return task

    async def approve(self, task_id: str, request: ApproveRequest) -> Task:
        task = self._require_task(task_id)
        if task.state != TaskState.WAITING_FOR_APPROVAL:
            raise ValueError("task is not waiting for approval")
        if task.approval_id != request.approval_id:
            raise PermissionError("approval_id is stale")
        if request.edits:
            task.values.update(request.edits)
            task.approval_id = str(uuid4())
            self.store.replace(task)
            await self._emit(
                task,
                "The edited details need fresh approval.",
                "बदली हुई जानकारी के लिए फिर से अनुमति चाहिए।",
                2,
                4,
                self._approval_data(task, "start"),
            )
            return task
        if task.approval_type == "start":
            task.state = TaskState.WORKING
            task.approval_id = None
            task.approval_type = None
            self.store.replace(task)
            await self._fill(task_id)
        else:
            task.state = TaskState.SUBMITTING
            task.approval_id = None
            task.approval_type = None
            self.store.replace(task)
            await self._submit(task_id)
        return task

    async def stop(self, task_id: str) -> Task:
        task = self._require_task(task_id)
        if task.state in {
            TaskState.DONE,
            TaskState.COULD_NOT_FINISH,
            TaskState.STOPPED,
            TaskState.OUTCOME_UNKNOWN,
        }:
            return task
        task.cancelled = True
        task.state = TaskState.STOPPED
        self.store.replace(task)
        await self._emit(
            task,
            "Stopped. Actions already taken may remain.",
            "रोक दिया गया। पहले किए गए काम का असर रह सकता है।",
            4,
            4,
        )
        return task

    async def events(self, task_id: str) -> AsyncIterator[TaskEvent]:
        task = self._require_task(task_id)
        queue: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        self._listeners.setdefault(task_id, []).append(queue)
        for event in self._history.get(task_id, []):
            await queue.put(event)
        if not self._history.get(task_id):
            await queue.put(self._snapshot_event(task))
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
                if event.state in {
                    TaskState.DONE,
                    TaskState.COULD_NOT_FINISH,
                    TaskState.STOPPED,
                    TaskState.OUTCOME_UNKNOWN,
                }:
                    return
        finally:
            self._listeners.get(task_id, []).remove(queue)

    async def _fill(self, task_id: str) -> None:
        task = self._require_task(task_id)
        await self._emit(
            task,
            "Filling the demo form.",
            "डेमो फ़ॉर्म भर रहा हूँ।",
            3,
            4,
            {"action": "Fill fields", "streaming_url": None},
        )
        result = await self.agent.run(
            self.flows[task.flow_id].url,
            json.dumps(task.values),
        )
        task = self._require_task(task_id)
        if task.cancelled:
            return
        if not result.ok or result.reported_fields is None:
            await self._fail(task, result.error or "mock agent failed")
            return
        task.reported_fields = result.reported_fields
        task.approval_id = str(uuid4())
        task.approval_type = "submit"
        task.state = TaskState.WAITING_FOR_APPROVAL
        self.store.replace(task)
        await self._emit(
            task,
            "Review the filled details before submitting.",
            "जमा करने से पहले भरी हुई जानकारी जाँचें।",
            3,
            4,
            self._approval_data(task, "submit"),
        )

    async def _submit(self, task_id: str) -> None:
        task = self._require_task(task_id)
        await self._emit(
            task,
            "Submitting the approved demo form.",
            "अनुमोदित डेमो फ़ॉर्म जमा कर रहा हूँ।",
            4,
            4,
            {"action": "Submit once", "streaming_url": None},
        )
        result = await self.agent.run(
            self.flows[task.flow_id].url,
            "Submit button exactly once",
        )
        task = self._require_task(task_id)
        if task.cancelled:
            return
        if result.ok:
            task.state = TaskState.DONE
            task.evidence = {
                "kind": "verified_confirmation",
                "text": result.final_text,
                "screenshot_url": result.screenshot_url,
            }
            self.store.replace(task)
            await self._emit(
                task,
                "The demo submission was completed.",
                "डेमो आवेदन जमा हो गया।",
                4,
                4,
                self._result_data(task, None),
            )
        else:
            await self._fail(task, result.error or "submission failed")

    async def _fail(self, task: Task, error: str) -> None:
        task.state = TaskState.COULD_NOT_FINISH
        task.error = error
        self.store.replace(task)
        await self._emit(
            task,
            "I could not complete the demo task.",
            "डेमो कार्य पूरा नहीं हो सका।",
            4,
            4,
            self._result_data(task, "agent_error"),
        )

    async def _emit(
        self,
        task: Task,
        message_en: str,
        message_hi: str,
        step: int,
        total_steps: int,
        data: dict | None = None,
    ) -> None:
        event = TaskEvent(
            task_id=task.task_id,
            state=task.state,
            message_en=message_en,
            message_hi=message_hi,
            step=step,
            total_steps=total_steps,
            data=data or {},
        )
        self._history.setdefault(task.task_id, []).append(event)
        for queue in self._listeners.get(task.task_id, []):
            await queue.put(event)

    def _approval_data(self, task: Task, approval_type: str) -> dict:
        flow = self.flows[task.flow_id]
        fields = [
            {
                "label_en": field.label_en,
                "label_hi": field.label_hi,
                "value": str(task.values.get(field.key, "")),
                "mismatch": False,
            }
            for field in flow.fields
        ]
        return {
            "approval_id": task.approval_id,
            "approval_type": approval_type,
            "site_kind": "demo",
            "flow_id": task.flow_id,
            "action_en": "Fill the demo form" if approval_type == "start" else "Submit the demo form",
            "action_hi": "डेमो फ़ॉर्म भरें" if approval_type == "start" else "डेमो फ़ॉर्म जमा करें",
            "data_notice_en": "These details will be sent to a cloud browser and entered on the demo form.",
            "data_notice_hi": "यह जानकारी क्लाउड ब्राउज़र को भेजकर डेमो फ़ॉर्म में भरी जाएगी।",
            "fields": fields,
            "read_back_en": "Please check these details.",
            "read_back_hi": "कृपया यह जानकारी जाँचें।",
        }

    def _result_data(self, task: Task, reason: str | None) -> dict:
        return {
            "evidence": task.evidence
            or {"kind": "agent_reported", "text": None, "screenshot_url": None},
            "summary_en": task.error or "Task completed.",
            "summary_hi": task.error or "कार्य पूरा हुआ।",
            "reason": reason,
            "needs_human_kind": None,
            "note": None,
        }

    def _snapshot_event(self, task: Task) -> TaskEvent:
        if task.state == TaskState.WAITING_FOR_APPROVAL:
            data = self._approval_data(task, task.approval_type or "start")
            message_en = "Review and approve the next action."
            message_hi = "अगले काम की जाँच करके अनुमति दें।"
        elif task.state in {
            TaskState.DONE,
            TaskState.COULD_NOT_FINISH,
            TaskState.STOPPED,
            TaskState.OUTCOME_UNKNOWN,
        }:
            data = self._result_data(task, task.error)
            message_en = "Task finished."
            message_hi = "कार्य समाप्त हुआ।"
        else:
            data = {}
            message_en = "Task is in progress."
            message_hi = "कार्य चल रहा है।"
        return TaskEvent(
            task_id=task.task_id,
            state=task.state,
            message_en=message_en,
            message_hi=message_hi,
            step=4 if task.state in {TaskState.DONE, TaskState.STOPPED} else 2,
            total_steps=4,
            data=data,
        )

    def _require_task(self, task_id: str) -> Task:
        task = self.store.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        return task


orchestrator = Orchestrator(TaskStore())
