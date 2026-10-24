import asyncio
import json
import logging
import re
import sqlite3
from collections.abc import AsyncIterator
from uuid import uuid4

from .agents.base import BrowserAgent, RunResult
from .agents.factory import create_browser_agent
from .agents.mock_agent import MockBrowserAgent
from .config import settings
from .flow_loader import load_flows
from .planner import (
    GeminiPlanner,
    Planner,
    PlannerConfigurationError,
    PlannerError,
    PlannerOutputError,
    PlannerResult,
)
from .schemas import (
    ApproveRequest,
    FieldType,
    FlowConfig,
    FlowField,
    Task,
    TaskEvent,
    TaskState,
)
from .task_store import TaskStore
from mock_site.store import MockStore, database_path


logger = logging.getLogger(__name__)
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


class Orchestrator:
    def __init__(
        self,
        store: TaskStore,
        agent: BrowserAgent | None = None,
        submission_store: MockStore | None = None,
        token_ttl_seconds: int | None = None,
        planner: Planner | None = None,
    ) -> None:
        self.store = store
        self.submission_store = submission_store or MockStore(database_path())
        self.agent = agent or create_browser_agent(
            settings.browser_agent,
            self.submission_store,
            settings.tinyfish_api_key,
            settings.tinyfish_base_url,
        )
        self.planner = planner or GeminiPlanner(
            settings.llm_api_key,
            settings.llm_model,
            provider=settings.llm_provider,
        )
        self.token_ttl_seconds = (
            settings.token_ttl_seconds
            if token_ttl_seconds is None
            else token_ttl_seconds
        )
        self.flows = load_flows()
        self._listeners: dict[str, list[asyncio.Queue[TaskEvent | None]]] = {}
        self._history: dict[str, list[TaskEvent]] = {}
        self._lock = asyncio.Lock()
        self._submission_runs: set[str] = set()
        self._planner_runs: dict[str, asyncio.Task[None]] = {}

    async def create_task(self, text: str, language: str) -> Task:
        task = Task(
            task_id=str(uuid4()),
            text=text,
            language=language,
        )
        self.store.create(task)
        await self._emit(
            task,
            "Understanding your request.",
            "आपका अनुरोध समझ रहा हूँ।",
            1,
            4,
        )
        self._schedule_planner(task.task_id)
        return self._require_task(task.task_id)

    async def answer(self, task_id: str, text: str) -> Task:
        async with self._lock:
            task = self._require_task(task_id)
            if task.state != TaskState.NEEDS_INFO:
                raise ValueError("task is not waiting for more information")
            task.text = f"{task.text}\n{text}".strip()
            task.state = TaskState.PLANNING
            task.clarifying_question_en = None
            task.clarifying_question_hi = None
            self.store.replace(task)
        await self._emit(
            task,
            "Updating the plan with your answer.",
            "आपके जवाब के साथ योजना अपडेट कर रहा हूँ।",
            1,
            4,
        )
        self._schedule_planner(task_id)
        return self._require_task(task_id)

    def _schedule_planner(self, task_id: str) -> None:
        task = self._require_task(task_id)
        if task.state != TaskState.PLANNING or task.cancelled:
            return
        planner_run = asyncio.create_task(self._run_planner(task_id))
        self._planner_runs[task_id] = planner_run
        planner_run.add_done_callback(
            lambda completed: self._planner_finished(task_id, completed)
        )

    def _planner_finished(
        self, task_id: str, completed: asyncio.Task[None]
    ) -> None:
        if self._planner_runs.get(task_id) is completed:
            self._planner_runs.pop(task_id, None)
        if completed.cancelled():
            return
        error = completed.exception()
        if error is not None:
            logger.error(
                "Unexpected planner failure for task %s",
                task_id,
                exc_info=(type(error), error, error.__traceback__),
            )
            asyncio.create_task(
                self._planner_failed(
                    task_id,
                    "The planner encountered an unexpected error. Please try again.",
                )
            )

    async def _run_planner(self, task_id: str) -> None:
        task = self._require_task(task_id)
        try:
            plan = await self.planner.plan(
                task.text,
                task.language,
                list(self.flows.values()),
                task.values,
            )
        except PlannerOutputError:
            await self._request_rephrase(task_id)
            return
        except PlannerConfigurationError as error:
            await self._planner_failed(task_id, str(error))
            return
        except PlannerError:
            await self._planner_failed(
                task_id, "The Gemini planner is unavailable. Please try again later."
            )
            return

        await self._apply_plan(task_id, plan)

    async def _apply_plan(self, task_id: str, plan: PlannerResult) -> None:
        async with self._lock:
            task = self._require_task(task_id)
            if task.state != TaskState.PLANNING or task.cancelled:
                return

            if plan.flow_id is None:
                task.state = TaskState.NEEDS_INFO
                task.clarifying_question_en = (
                    plan.clarifying_question_en
                    or "What would you like help with? I can fill the demo form."
                )
                task.clarifying_question_hi = (
                    plan.clarifying_question_hi
                    or "आप किस काम में मदद चाहते हैं? मैं डेमो फ़ॉर्म भर सकता हूँ।"
                )
                self.store.replace(task)
                event_data = self._needs_info_data(task)
                event_messages = (
                    task.clarifying_question_en,
                    task.clarifying_question_hi,
                )
            elif plan.flow_id not in self.flows:
                task.state = TaskState.NEEDS_INFO
                task.clarifying_question_en = (
                    "That task is not available yet. Would you like help with the "
                    "demo application form?"
                )
                task.clarifying_question_hi = (
                    "यह काम अभी उपलब्ध नहीं है। क्या आप डेमो आवेदन फ़ॉर्म में मदद चाहते हैं?"
                )
                self.store.replace(task)
                event_data = self._needs_info_data(task)
                event_messages = (
                    task.clarifying_question_en,
                    task.clarifying_question_hi,
                )
            elif task.flow_id is not None and task.flow_id != plan.flow_id:
                task.state = TaskState.NEEDS_INFO
                task.clarifying_question_en = (
                    "Please start a new request if you want to switch to a different task."
                )
                task.clarifying_question_hi = (
                    "दूसरे काम पर जाने के लिए कृपया नया अनुरोध शुरू करें।"
                )
                self.store.replace(task)
                event_data = self._needs_info_data(task)
                event_messages = (
                    task.clarifying_question_en,
                    task.clarifying_question_hi,
                )
            else:
                flow = self.flows[plan.flow_id]
                fields = {field.key: field for field in flow.fields}
                unknown_values = set(plan.values) - fields.keys()
                unknown_missing = set(plan.missing) - fields.keys()
                if unknown_values or unknown_missing:
                    task.state = TaskState.NEEDS_INFO
                    task.clarifying_question_en = (
                        "I could not match some details to this form. Please rephrase "
                        "your request using the form fields."
                    )
                    task.clarifying_question_hi = (
                        "कुछ जानकारी इस फ़ॉर्म से मेल नहीं खा सकी। कृपया फ़ॉर्म के "
                        "विवरणों के अनुसार अपना अनुरोध फिर से बताएं।"
                    )
                    self.store.replace(task)
                    event_data = self._needs_info_data(task)
                    event_messages = (
                        task.clarifying_question_en,
                        task.clarifying_question_hi,
                    )
                else:
                    task.flow_id = plan.flow_id
                    task.language = (
                        task.language if task.language != "auto" else plan.language
                    )
                    values = dict(task.values)
                    invalid_fields: set[str] = set()
                    for key, value in plan.values.items():
                        try:
                            values[key] = self._validate_field_value(fields[key], value)
                        except ValueError:
                            values.pop(key, None)
                            invalid_fields.add(key)

                    missing = [
                        field.key
                        for field in flow.fields
                        if field.key not in values
                        and (field.required or field.key in plan.missing)
                    ]
                    missing.extend(
                        field.key
                        for field in flow.fields
                        if field.key in invalid_fields and field.key not in missing
                    )
                    task.values = values
                    task.missing = missing
                    if missing or any(key in invalid_fields for key in fields):
                        task.state = TaskState.NEEDS_INFO
                        if invalid_fields:
                            labels_en = ", ".join(
                                fields[key].label_en for key in sorted(invalid_fields)
                            )
                            labels_hi = ", ".join(
                                fields[key].label_hi for key in sorted(invalid_fields)
                            )
                            task.clarifying_question_en = (
                                f"Please provide valid details for: {labels_en}."
                            )
                            task.clarifying_question_hi = (
                                f"कृपया इन विवरणों की सही जानकारी दें: {labels_hi}।"
                            )
                        else:
                            task.clarifying_question_en = (
                                plan.clarifying_question_en
                                or self._missing_question(flow, missing, "en")
                            )
                            task.clarifying_question_hi = (
                                plan.clarifying_question_hi
                                or self._missing_question(flow, missing, "hi")
                            )
                        self.store.replace(task)
                        event_data = self._needs_info_data(task)
                        event_messages = (
                            task.clarifying_question_en,
                            task.clarifying_question_hi,
                        )
                    else:
                        task.missing = []
                        task.clarifying_question_en = None
                        task.clarifying_question_hi = None
                        task.approval_id = str(uuid4())
                        task.approval_type = "start"
                        task.state = TaskState.WAITING_FOR_APPROVAL
                        self.store.replace(task)
                        event_data = self._approval_data(task, "start")
                        event_messages = (
                            "Please review and approve starting the demo form.",
                            "डेमो फ़ॉर्म शुरू करने की जानकारी जाँचकर अनुमति दें।",
                        )

        await self._emit(
            task,
            event_messages[0],
            event_messages[1],
            2,
            4,
            event_data,
        )

    async def _request_rephrase(self, task_id: str) -> None:
        async with self._lock:
            task = self._require_task(task_id)
            if task.state != TaskState.PLANNING or task.cancelled:
                return
            task.state = TaskState.NEEDS_INFO
            task.clarifying_question_en = (
                "I could not understand that request. Please rephrase it."
            )
            task.clarifying_question_hi = (
                "मैं यह अनुरोध समझ नहीं पाया। कृपया इसे दूसरे शब्दों में बताएं।"
            )
            self.store.replace(task)
        await self._emit(
            task,
            task.clarifying_question_en,
            task.clarifying_question_hi,
            2,
            4,
            self._needs_info_data(task),
        )

    async def _planner_failed(self, task_id: str, error: str) -> None:
        async with self._lock:
            task = self._require_task(task_id)
            if task.state != TaskState.PLANNING or task.cancelled:
                return
            task.state = TaskState.COULD_NOT_FINISH
            task.error = error
            task.error_hi = (
                "योजना सेवा उपलब्ध नहीं है। कृपया API सेटिंग जाँचें और फिर कोशिश करें।"
            )
            self.store.replace(task)
        await self._emit(
            task,
            task.error,
            task.error_hi,
            4,
            4,
            self._result_data(task, "planner_unavailable"),
        )

    @staticmethod
    def _needs_info_data(task: Task) -> dict:
        return {
            "question_en": task.clarifying_question_en,
            "question_hi": task.clarifying_question_hi,
            "missing": task.missing,
        }

    @staticmethod
    def _missing_question(flow: FlowConfig, missing: list[str], language: str) -> str:
        labels = [
            flow_field.label_hi if language == "hi" else flow_field.label_en
            for flow_field in flow.fields
            if flow_field.key in missing
        ]
        joined = ", ".join(labels)
        if language == "hi":
            return f"कृपया यह जानकारी दें: {joined}।"
        return f"Please provide: {joined}."

    async def approve(self, task_id: str, request: ApproveRequest) -> Task:
        operation: str | None = None
        token: str | None = None
        approval_event: Task | None = None
        async with self._lock:
            task = self._require_task(task_id)
            if task.state != TaskState.WAITING_FOR_APPROVAL:
                raise ValueError("task is not waiting for approval")
            if task.approval_id != request.approval_id:
                raise PermissionError("approval_id is stale")
            if request.edits is not None:
                task.values.update(self._validate_edits(task, request.edits))
                task.reported_fields = None
                task.approval_id = str(uuid4())
                task.approval_type = "start"
                self.store.replace(task)
                approval_event = task
            elif task.approval_type == "start":
                task.state = TaskState.WORKING
                task.approval_id = None
                task.approval_type = None
                self.store.replace(task)
                operation = "fill"
            elif task.approval_type == "submit":
                if not self._reported_fields_match(task):
                    raise ValueError(
                        "reported form values do not match the reviewed values; "
                        "edit the details to refill the form before submitting"
                    )
                token = self.submission_store.issue_token(
                    task_id, task.values, self.token_ttl_seconds
                )
                task.state = TaskState.SUBMITTING
                task.approval_id = None
                task.approval_type = None
                self.store.replace(task)
                operation = "submit"
            else:
                raise ValueError("task has no valid approval action")

        if approval_event is not None:
            await self._emit(
                approval_event,
                "The edited details need fresh approval.",
                "बदली हुई जानकारी के लिए फिर से अनुमति चाहिए।",
                2,
                4,
                self._approval_data(approval_event, "start"),
            )
        elif operation == "fill":
            await self._fill(task_id)
        elif operation == "submit" and token is not None:
            await self._submit(task_id, token)
        return self._require_task(task_id)

    async def stop(self, task_id: str) -> Task:
        async with self._lock:
            task = self._require_task(task_id)
            if task.state in {
                TaskState.DONE,
                TaskState.COULD_NOT_FINISH,
                TaskState.STOPPED,
                TaskState.OUTCOME_UNKNOWN,
            }:
                return task
            task.cancelled = True
            if task.state == TaskState.PLANNING:
                planner_run = self._planner_runs.get(task_id)
                if planner_run is not None:
                    planner_run.cancel()
            self.submission_store.revoke_task_tokens(task_id, "user_stopped")
            verification_pending = (
                task.state == TaskState.SUBMITTING
                and task_id in self._submission_runs
            )
            if not verification_pending:
                task.state = TaskState.STOPPED
            self.store.replace(task)
        if verification_pending:
            await self._emit(
                task,
                "Stop requested during submission. Checking whether it was received.",
                "जमा करते समय रोकने का अनुरोध मिला। पुष्टि की जाँच हो रही है।",
                4,
                4,
            )
        else:
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
        flow = self.flows[task.flow_id]
        await self._emit(
            task,
            "Filling the demo form.",
            "डेमो फ़ॉर्म भर रहा हूँ।",
            3,
            4,
            {"action": "Fill fields", "streaming_url": None},
        )
        goal = self._format_goal(flow.goal_template, flow, task.values)
        if isinstance(self.agent, MockBrowserAgent):
            goal = self._with_mock_context(
                goal, "fill", task.task_id, task.values
            )
        result = await self.agent.run(flow.url, goal)
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
        approval_data = self._approval_data(task, "submit")
        if result.streaming_url:
            approval_data["streaming_url"] = result.streaming_url
        if result.screenshot_url:
            approval_data["screenshot_url"] = result.screenshot_url
        await self._emit(
            task,
            "Review the filled details before submitting.",
            "जमा करने से पहले भरी हुई जानकारी जाँचें।",
            3,
            4,
            approval_data,
        )

    async def _submit(self, task_id: str, token: str) -> None:
        task = self._require_task(task_id)
        if task.cancelled:
            return
        await self._emit(
            task,
            "Submitting the approved demo form.",
            "अनुमोदित डेमो फ़ॉर्म जमा कर रहा हूँ।",
            4,
            4,
            {"action": "Submit once", "streaming_url": None},
        )
        task = self._require_task(task_id)
        if task.cancelled:
            return
        flow = self.flows[task.flow_id]
        goal = self._format_goal(
            flow.submit_goal_template or "", flow, task.values, token
        )
        if isinstance(self.agent, MockBrowserAgent):
            goal = self._with_mock_context(
                goal, "submit", task.task_id, task.values, token
            )
        self._submission_runs.add(task_id)
        try:
            try:
                result = await self.agent.run(flow.url, goal)
            except Exception as error:
                logger.exception(
                    "Submission agent failed for task %s; checking authoritative status",
                    task_id,
                )
                result = RunResult(
                    False,
                    "submission-agent-error",
                    error=f"submission agent failed: {error}",
                )
        finally:
            self._submission_runs.discard(task_id)
        task = self._require_task(task_id)
        try:
            verified = self.submission_store.verify_submission(
                task_id, token, task.values
            )
        except sqlite3.Error:
            logger.exception("Unable to verify demo submission for task %s", task_id)
            verified = None

        if verified is not None:
            task.state = TaskState.DONE
            task.evidence = {
                "kind": "verified_confirmation",
                "text": (
                    "Application received. Reference number: "
                    f"{verified.reference_number}"
                ),
                "screenshot_url": result.screenshot_url,
            }
            self.store.replace(task)
            await self._emit(
                task,
                "The demo submission was completed.",
                "डेमो आवेदन जमा हो गया।",
                4,
                4,
                {
                    **self._result_data(
                        task,
                        None,
                        (
                            "The submission was verified after a stop request."
                            if task.cancelled
                            else None
                        ),
                    ),
                    "streaming_url": result.streaming_url,
                },
            )
        else:
            self.submission_store.revoke_task_tokens(task_id, "verification_failed")
            task.state = TaskState.OUTCOME_UNKNOWN
            task.error = (
                "The demo site did not provide a server-verified submission record. "
                "Do not retry automatically; check the demo site before taking action."
            )
            task.evidence = {
                "kind": "agent_reported",
                "text": result.final_text,
                "screenshot_url": result.screenshot_url,
            }
            self.store.replace(task)
            await self._emit(
                task,
                "I could not verify whether the demo submission was received. "
                "Do not retry; check the demo site first.",
                "डेमो जमा होने की पुष्टि नहीं हो सकी। दोबारा न भेजें; पहले डेमो साइट जाँचें।",
                4,
                4,
                {
                    **self._result_data(task, "verification_failed"),
                    "streaming_url": result.streaming_url,
                },
            )

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
                "value": str(
                    (
                        task.reported_fields.get(field.key, "")
                        if approval_type == "submit" and task.reported_fields is not None
                        else task.values.get(field.key, "")
                    )
                ),
                "mismatch": (
                    task.reported_fields is not None
                    and str(task.reported_fields.get(field.key, ""))
                    != str(task.values.get(field.key, ""))
                ),
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

    def _result_data(
        self, task: Task, reason: str | None, note: str | None = None
    ) -> dict:
        return {
            "evidence": task.evidence
            or {"kind": "agent_reported", "text": None, "screenshot_url": None},
            "summary_en": task.error or "Task completed.",
            "summary_hi": (
                "डेमो जमा हुआ या नहीं, इसकी सर्वर से पुष्टि नहीं हो सकी। "
                "दोबारा न भेजें; पहले डेमो साइट जाँचें।"
                if task.state == TaskState.OUTCOME_UNKNOWN
                else task.error_hi or task.error or "कार्य पूरा हुआ।"
            ),
            "reason": reason,
            "needs_human_kind": None,
            "note": note,
        }

    def _snapshot_event(self, task: Task) -> TaskEvent:
        if task.state == TaskState.NEEDS_INFO:
            data = self._needs_info_data(task)
            message_en = task.clarifying_question_en or "Please provide more information."
            message_hi = task.clarifying_question_hi or "कृपया अधिक जानकारी दें।"
        elif task.state == TaskState.WAITING_FOR_APPROVAL:
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

    def _validate_edits(self, task: Task, edits: dict[str, str | int]) -> dict[str, str | int]:
        if task.flow_id is None:
            raise ValueError("task has no selected flow")
        flow = self.flows[task.flow_id]
        fields = {field.key: field for field in flow.fields}
        unknown = set(edits) - fields.keys()
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")

        validated: dict[str, str | int] = {}
        for key, value in edits.items():
            validated[key] = self._validate_field_value(fields[key], value)
        return validated

    @staticmethod
    def _validate_field_value(field: FlowField, value: str | int) -> str | int:
        if isinstance(value, bool):
            raise ValueError(f"{field.key} has an invalid type")
        if field.type == FieldType.NUMBER:
            if not isinstance(value, (str, int)):
                raise ValueError(f"{field.key} must be a whole number")
            text = str(value).strip().translate(DEVANAGARI_DIGITS)
            if field.pattern and not re.fullmatch(field.pattern, text):
                raise ValueError(f"{field.key} has an invalid format")
            if not re.fullmatch(r"[0-9]+", text):
                raise ValueError(f"{field.key} must be a whole number")
            number = int(text)
            if field.min is not None and number < field.min:
                raise ValueError(f"{field.key} is below the minimum")
            if field.max is not None and number > field.max:
                raise ValueError(f"{field.key} is above the maximum")
            return number

        if not isinstance(value, str):
            raise ValueError(f"{field.key} must be text")
        text = value.strip().translate(DEVANAGARI_DIGITS)
        if field.required and not text:
            raise ValueError(f"{field.key} is required")
        if field.max_len is not None and len(text) > field.max_len:
            raise ValueError(f"{field.key} exceeds the maximum length")
        if field.pattern and not re.fullmatch(field.pattern, text):
            raise ValueError(f"{field.key} has an invalid format")
        return text

    def _reported_fields_match(self, task: Task) -> bool:
        if task.reported_fields is None:
            return False
        flow = self.flows[task.flow_id]
        return all(
            field.key in task.reported_fields
            and str(task.reported_fields[field.key]).strip()
            == str(task.values.get(field.key, "")).strip()
            for field in flow.fields
            if field.required
        )

    @staticmethod
    def _format_goal(
        template: str,
        flow: FlowConfig,
        values: dict[str, str | int],
        approval_code: str | None = None,
    ) -> str:
        field_lines = "\n".join(
            f"- {field.label_en}: {values.get(field.key, '')}"
            for field in flow.fields
        )
        goal = template.replace("{{field_lines}}", field_lines)
        if approval_code is not None:
            goal = goal.replace("{{approval_code}}", approval_code)
        return goal

    @staticmethod
    def _with_mock_context(
        goal: str,
        operation: str,
        task_id: str,
        payload: dict[str, str | int],
        approval_code: str | None = None,
    ) -> str:
        context = {
            "operation": operation,
            "task_id": task_id,
            "payload": payload,
            "approval_code": approval_code,
        }
        return f"{goal}\n\n{MockBrowserAgent.MOCK_CONTEXT}{json.dumps(context)}"


orchestrator = Orchestrator(
    TaskStore(),
    planner=GeminiPlanner(
        settings.llm_api_key,
        settings.llm_model,
        provider=settings.llm_provider,
    ),
)
