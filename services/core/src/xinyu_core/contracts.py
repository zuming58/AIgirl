from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventEnvelope(ApiModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    timestamp: datetime = Field(default_factory=utc_now)
    session_id: str | None = None
    turn_id: str | None = None
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    payload: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ready", "error"]
    provider: str


class RuntimeComponent(ApiModel):
    id: str
    kind: Literal["core", "llm", "stt", "tts", "avatar"]
    status: Literal["ready", "degraded", "unavailable", "disabled"]
    detail: str
    required: bool = False


class ModelRuntimeBudget(ApiModel):
    gpu_budget_mb: int = Field(ge=0)
    llm_max_mb: int = Field(ge=0)
    stt_max_mb: int = Field(ge=0)
    tts_max_mb: int = Field(ge=0)
    avatar_max_mb: int = Field(ge=0)


class ModelRuntimePlan(ApiModel):
    profile: Literal["quality_local", "quality_cloud_llm", "safe_fallback"]
    status: Literal["ready", "degraded"]
    budget: ModelRuntimeBudget
    validation_errors: list[str] = Field(default_factory=list)
    components: list[RuntimeComponent]


class RuntimeStatus(ApiModel):
    status: Literal["ready", "degraded"]
    started_at: datetime
    components: list[RuntimeComponent]
    model_plan: ModelRuntimePlan


AvatarState = Literal[
    "idle",
    "listening",
    "thinking",
    "speaking",
    "smiling",
    "goodnight",
]


class AvatarStateUpdate(ApiModel):
    state: AvatarState
    emotion: str = Field(default="calm", min_length=1, max_length=40)
    intensity: float = Field(default=0.35, ge=0, le=1)


class AvatarStatus(AvatarStateUpdate):
    character_id: str
    renderer: Literal["static_fallback", "video_state_library", "realtime_lipsync"]
    available_states: list[AvatarState] = Field(default_factory=list)
    target_resolution: str
    target_fps: int
    fallback_reason: str | None = None


class GpuCapability(ApiModel):
    name: str
    memory_mb: int


class SystemCapabilities(ApiModel):
    platform: str
    cpu: str
    logical_cores: int
    memory_gb: float
    gpus: list[GpuCapability] = Field(default_factory=list)
    recommended_profile: Literal[
        "high_quality_24gb",
        "high_quality_16gb",
        "balanced_10gb",
        "cpu_compatibility",
    ]
    avatar_strategy: str
    notes: list[str] = Field(default_factory=list)


class ModelRecord(ApiModel):
    id: str
    kind: str
    provider: str
    status: str
    required: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(ApiModel):
    message: str = Field(min_length=1, max_length=12_000)
    session_id: str | None = None
    channel: Literal["text", "voice"] = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageRecord(ApiModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSummary(ApiModel):
    id: str
    channel: str
    status: str
    started_at: datetime
    last_active_at: datetime
    message_count: int
    last_message: str


class ChatResponse(ApiModel):
    session_id: str
    turn_id: str
    trace_id: str
    reply: str
    provider: str
    user_message: MessageRecord
    assistant_message: MessageRecord
    memory_candidates: list[str] = Field(default_factory=list)


MemoryKind = Literal["profile", "preference", "concern", "episode", "commitment"]


class MemoryCreate(ApiModel):
    kind: MemoryKind
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=8_000)
    source: Literal["user_explicit", "tool_result", "system_inference"] = "user_explicit"
    source_message_id: str | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)
    salience: float = Field(default=0.5, ge=0, le=1)
    user_confirmed: bool = False
    sensitivity: Literal["normal", "private", "sensitive"] = "normal"
    starred: bool = False


class MemoryUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, min_length=1, max_length=8_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    salience: float | None = Field(default=None, ge=0, le=1)
    user_confirmed: bool | None = None
    sensitivity: Literal["normal", "private", "sensitive"] | None = None
    starred: bool | None = None


class MemoryRecord(MemoryCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    valid_from: datetime
    valid_to: datetime | None = None
    supersedes_id: str | None = None


class MemoryContext(ApiModel):
    memory_id: str
    explanation: str
    source_message: MessageRecord | None = None
    superseded_memory: MemoryRecord | None = None


class MemoryQuery(ApiModel):
    query: str = Field(default="", max_length=1_000)
    kinds: list[MemoryKind] = Field(default_factory=list)
    starred_only: bool = False
    include_sensitive: bool = False
    limit: int = Field(default=50, ge=1, le=200)


class MemoryIndexStatus(ApiModel):
    status: Literal["ready", "building", "degraded", "disabled"]
    model: str | None = None
    dimensions: int | None = None
    indexed_count: int = 0
    pending_count: int = 0
    last_error: str | None = None


class MemoryIndexRebuildResponse(ApiModel):
    status: Literal["building", "disabled"]
    pending_count: int


class ConversationSummaryRecord(ApiModel):
    id: str
    session_id: str
    first_message_id: str
    last_message_id: str
    message_count: int
    content: str
    status: Literal["pending", "ready", "failed", "unavailable", "deleted"]
    provider: str | None = None
    model: str | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ConversationSummaryList(ApiModel):
    items: list[ConversationSummaryRecord]
    total: int


class PlanCreate(ApiModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4_000)
    category: Literal["work", "life", "promise"] = "life"
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    source: Literal["user", "assistant", "tool"] = "user"


class PlanUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4_000)
    category: Literal["work", "life", "promise"] | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    status: Literal["pending", "running", "completed", "cancelled"] | None = None


class PlanRecord(PlanCreate):
    id: str
    status: Literal["pending", "running", "completed", "cancelled"]
    progress: float
    created_at: datetime
    updated_at: datetime


class NotificationRecord(ApiModel):
    id: str
    event_type: str
    reason: str
    payload: dict[str, Any]
    status: Literal["dispatching", "delivered", "acknowledged"]
    scheduled_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime


class PersonaUpdate(ApiModel):
    name: str = Field(default="心屿", min_length=1, max_length=40)
    relationship_role: str = Field(default="companion", max_length=80)
    background: str = Field(default="", max_length=8_000)
    voice: dict[str, Any] = Field(default_factory=dict)
    behavior: dict[str, Any] = Field(default_factory=dict)
    boundaries: dict[str, Any] = Field(default_factory=dict)


class PersonaRecord(PersonaUpdate):
    id: str
    version: int
    active: bool
    created_at: datetime


class MoodUpdate(ApiModel):
    valence: float = Field(ge=-1, le=1)
    arousal: float = Field(ge=0, le=1)
    energy: float = Field(ge=0, le=1)
    closeness: float = Field(ge=0, le=1)
    stress: float = Field(ge=0, le=1)
    reason: str = Field(default="user_adjusted", max_length=240)


class MoodRecord(MoodUpdate):
    id: str
    created_at: datetime


class SettingUpdate(ApiModel):
    value: Any


class VoiceSessionResponse(ApiModel):
    session_id: str
    status: Literal["ready", "degraded"]
    transport: Literal["websocket"]
    endpoint: str
    provider: str
    detail: str


class VoiceTranscriptCreate(ApiModel):
    session_id: str = Field(min_length=1, max_length=160)
    transcript_id: str = Field(min_length=1, max_length=240)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiagnosticReport(ApiModel):
    generated_at: datetime = Field(default_factory=utc_now)
    app_version: str
    database: dict[str, Any]
    counts: dict[str, int]
    runtime: RuntimeStatus
    system: SystemCapabilities
    privacy: dict[str, Any]


class DataExport(ApiModel):
    schema_version: int
    exported_at: datetime
    data: dict[str, list[dict[str, Any]]]


class BackupRecord(ApiModel):
    name: str
    created_at: datetime
    size_bytes: int


class ConfirmAction(ApiModel):
    confirmed: bool = False


class RestoreResult(ApiModel):
    restored_from: str
    safety_backup: BackupRecord
    restored_at: datetime


class DataImportRequest(ApiModel):
    schema_version: int
    exported_at: datetime | None = None
    data: dict[str, list[dict[str, Any]]]
    confirmed: bool = False


class DataImportResult(ApiModel):
    imported_rows: int
    safety_backup: BackupRecord
    imported_at: datetime
