from enum import StrEnum
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    url: str | None = Field(default=None, min_length=1, max_length=2000)
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

    @model_validator(mode="after")
    def browser_target_required(self) -> "FlowConfig":
        if self.id == "web_discovery":
            if self.url is not None:
                raise ValueError(
                    "web_discovery uses grounded search and cannot define a browser URL"
                )
        elif self.url is None:
            raise ValueError("browser flows require a URL")
        return self


class DiscoveryScheme(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    description_hi: str | None = Field(default=None, max_length=2000)
    scheme_page_url: str | None = Field(default=None, max_length=2000)


class DiscoveryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schemes: list[DiscoveryScheme] = Field(max_length=10)
    problems: list[str] = Field(max_length=20)


class WebsiteCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=500)
    confidence: Literal["high", "medium", "low"]


class WebsiteResolutionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidates: list[WebsiteCandidate] = Field(max_length=5)
    problems: list[str] = Field(max_length=10)


class WebsiteSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)


class WebsiteMedia(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)


class WebsiteResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str = Field(min_length=1, max_length=5000)
    sources: list[WebsiteSource] = Field(min_length=1, max_length=10)
    media: list[WebsiteMedia] = Field(default_factory=list, max_length=10)


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


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=2000)


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    state: TaskState = TaskState.PLANNING
    requested_flow: Literal["auto", "demo", "discovery", "web"] = "auto"
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list, max_length=12, exclude=True
    )
    flow_id: str | None = None
    values: dict[str, str | int] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    cancelled: bool = False
    approval_id: str | None = None
    approval_type: Literal["start", "submit", "web"] | None = None
    text: str = ""
    language: Literal["hi", "en", "auto"] = "auto"
    reported_fields: dict[str, str] | None = None
    evidence: dict[str, Any] | None = None
    schemes: list[DiscoveryScheme] = Field(default_factory=list)
    web_phase: Literal["site_name", "site_choice", "question"] | None = None
    web_candidates: list[WebsiteCandidate] = Field(default_factory=list)
    selected_site_url: str | None = None
    web_query: str | None = None
    web_answer: str | None = None
    web_sources: list[WebsiteSource] = Field(default_factory=list)
    web_media: list[WebsiteMedia] = Field(default_factory=list)
    reason: str | None = None
    needs_human_kind: Literal["captcha", "otp", "login", "blocked"] | None = None
    human_action_url: str | None = None
    error: str | None = None
    error_hi: str | None = None
    clarifying_question_en: str | None = None
    clarifying_question_hi: str | None = None
    assistant_response_en: str | None = None
    assistant_response_hi: str | None = None


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    lang: Literal["hi", "en", "auto"] = "auto"
    flow: Literal["auto", "demo", "discovery", "web"] = "auto"
    history: list[ConversationTurn] = Field(default_factory=list, max_length=12)


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
