from enum import StrEnum
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FlowType(StrEnum):
    DISCOVERY = "discovery"
    SUBMISSION = "submission"


class FieldType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"


class FlowField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    label_en: str = Field(min_length=1, max_length=100)
    label_hi: str = Field(min_length=1, max_length=100)
    required: bool = True
    type: FieldType
    max_len: int | None = Field(default=None, ge=1, le=1000)
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)
    pattern: str | None = Field(default=None, max_length=200)


class SystemField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    source: Literal["orchestrator"]
    shown_to_user: bool = False


class FlowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    flow_type: FlowType
    title_en: str = Field(min_length=1, max_length=200)
    title_hi: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    goal_template: str = Field(min_length=1, max_length=10000)
    submit_goal_template: str | None = Field(default=None, max_length=10000)
    fields: list[FlowField] = Field(default_factory=list)
    sensitive_fields: list[str] = Field(default_factory=list)
    system_fields: list[SystemField] = Field(default_factory=list)
    success_markers: list[str] = Field(default_factory=list)
    needs_human: list[Literal["captcha", "otp", "login", "blocked"]] = Field(
        default_factory=list
    )

    @field_validator("submit_goal_template")
    @classmethod
    def submission_template_required(cls, value: str | None, info: Any) -> str | None:
        if info.data.get("flow_type") == FlowType.SUBMISSION and not value:
            raise ValueError("submission flows require submit_goal_template")
        if info.data.get("flow_type") == FlowType.DISCOVERY and value:
            raise ValueError("discovery flows cannot define submit_goal_template")
        return value


class TaskState(StrEnum):
    PLANNING = "planning"
    NEEDS_INFO = "needs_info"
    WORKING = "working"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    SUBMITTING = "submitting"
    DONE = "done"
    COULD_NOT_FINISH = "could_not_finish"
    STOPPED = "stopped"
    OUTCOME_UNKNOWN = "outcome_unknown"


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    state: TaskState = TaskState.PLANNING
    flow_id: str | None = None
    values: dict[str, str | int] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    cancelled: bool = False
    approval_id: str | None = None
    approval_type: Literal["start", "submit"] | None = None
    text: str = ""
    language: Literal["hi", "en", "auto"] = "auto"
    reported_fields: dict[str, str] | None = None
    evidence: dict[str, Any] | None = None
    error: str | None = None
    error_hi: str | None = None
    clarifying_question_en: str | None = None
    clarifying_question_hi: str | None = None


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    lang: Literal["hi", "en", "auto"] = "auto"


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(min_length=1, max_length=100)
    edits: dict[str, str | int] | None = None


class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: TaskState
    message_en: str
    message_hi: str
    step: int
    total_steps: int
    data: dict[str, Any] = Field(default_factory=dict)
