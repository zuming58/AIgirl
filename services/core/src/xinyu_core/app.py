from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from websockets.asyncio.client import connect as websocket_connect

from .config import AppConfig
from .contracts import (
    AvatarStateUpdate,
    AvatarStatus,
    ChatRequest,
    ChatResponse,
    BackupRecord,
    ConfirmAction,
    ConversationSummary,
    ConversationSummaryList,
    ConversationSummaryRecord,
    DataExport,
    DataImportRequest,
    DataImportResult,
    DiagnosticReport,
    EventEnvelope,
    HealthResponse,
    MemoryCreate,
    MemoryContext,
    MemoryIndexRebuildResponse,
    MemoryIndexStatus,
    MemoryQuery,
    MemoryRecord,
    MemoryUpdate,
    MessageRecord,
    ModelRecord,
    MoodRecord,
    MoodUpdate,
    NotificationRecord,
    PersonaRecord,
    PersonaUpdate,
    PlanCreate,
    PlanRecord,
    PlanUpdate,
    RuntimeStatus,
    RestoreResult,
    SettingUpdate,
    SystemCapabilities,
    VoiceTranscriptCreate,
    VoiceSessionResponse,
)
from .avatar import AvatarRuntime
from .database import Database
from .diagnostics import inspect_system
from .events import EventHub
from .embeddings import create_embedding_provider
from .memory_intelligence import MemoryIntelligenceService
from .model_manager import ModelManager
from .providers import create_provider
from .reminders import ReminderScheduler
from .repository import Repository
from .services import ChatService
from .summaries import ConversationSummaryService, create_summary_provider
from .speech import SpeechRuntime, relay_voice_messages


def create_app(config: AppConfig | None = None) -> FastAPI:
    config = config or AppConfig.from_env()
    database = Database(config.database_path)
    repository = Repository(database)
    event_hub = EventHub()
    provider = create_provider(config)
    embedding_provider = create_embedding_provider(config)
    memory_intelligence = MemoryIntelligenceService(repository, embedding_provider)
    summary_service = ConversationSummaryService(
        repository,
        create_summary_provider(config),
    )
    speech_runtime = SpeechRuntime(config.speech_realtime_url)
    avatar_runtime = AvatarRuntime(config.data_dir)
    model_manager = ModelManager(
        config,
        inspect_system(),
        speech_runtime,
        avatar_runtime,
    )
    chat_service = ChatService(
        repository,
        provider,
        event_hub,
        memory_intelligence,
        summary_service,
    )
    reminder_scheduler = ReminderScheduler(repository, event_hub)
    started_at = datetime.now(timezone.utc)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        for model_id, (provider_id, status, metadata) in (
            model_manager.model_metadata().items()
        ):
            repository.set_model_status(
                model_id,
                provider_id,
                status,
                metadata,
            )
        avatar_status = avatar_runtime.status()
        repository.set_model_status(
            "avatar-local",
            avatar_status.renderer,
            "ready" if avatar_status.renderer != "static_fallback" else "degraded",
            {
                "character_id": avatar_status.character_id,
                "available_states": avatar_status.available_states,
                "target_resolution": avatar_status.target_resolution,
                "target_fps": avatar_status.target_fps,
                "detail": avatar_status.fallback_reason,
            },
        )
        repository.expire_stale_memories()
        summary_service.recover_pending()
        index_status = memory_intelligence.status()
        if embedding_provider.configured and (
            index_status.pending_count > 0
            or index_status.status in {"degraded", "disabled"}
            or index_status.model != embedding_provider.model
        ):
            memory_intelligence.rebuild()
        reminder_scheduler.start()
        try:
            yield
        finally:
            await reminder_scheduler.stop()
            await memory_intelligence.close()
            await summary_service.close()

    app = FastAPI(
        title="Xinyu Core API",
        version=config.app_version,
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.database = database
    app.state.repository = repository
    app.state.events = event_hub
    app.state.chat_service = chat_service
    app.state.memory_intelligence = memory_intelligence
    app.state.summary_service = summary_service
    app.state.reminder_scheduler = reminder_scheduler
    app.state.avatar_runtime = avatar_runtime
    app.state.model_manager = model_manager
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "tauri://localhost",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def authorize(
        authorization: str | None = Header(default=None),
    ) -> None:
        if not config.auth_token:
            return
        if authorization != f"Bearer {config.auth_token}":
            raise HTTPException(status_code=401, detail="Invalid local session token")

    async def commit_avatar_state(value: AvatarStateUpdate) -> AvatarStatus:
        status = avatar_runtime.set_state(value)
        await event_hub.publish(
            EventEnvelope(
                type="avatar.state.changed",
                payload=status.model_dump(mode="json"),
            )
        )
        return status

    @app.get("/health", response_model=HealthResponse)
    def health(_: None = Depends(authorize)) -> HealthResponse:
        ready = database.ping()
        return HealthResponse(
            status="ok" if ready else "degraded",
            version=config.app_version,
            database="ready" if ready else "error",
            provider=provider.id,
        )

    @app.get("/v1/runtime/status", response_model=RuntimeStatus)
    def runtime_status(_: None = Depends(authorize)) -> RuntimeStatus:
        return current_runtime_status()

    @app.get("/v1/system/capabilities", response_model=SystemCapabilities)
    def system_capabilities(
        _: None = Depends(authorize),
    ) -> SystemCapabilities:
        return inspect_system()

    def current_runtime_status() -> RuntimeStatus:
        plan = model_manager.plan()
        components = plan.components
        degraded = any(
            item.required and item.status != "ready" for item in components
        ) or plan.status != "ready"
        return RuntimeStatus(
            status="degraded" if degraded else "ready",
            started_at=started_at,
            components=components,
            model_plan=plan,
        )

    @app.get("/v1/diagnostics", response_model=DiagnosticReport)
    def diagnostics(_: None = Depends(authorize)) -> DiagnosticReport:
        settings = repository.get_settings()
        return DiagnosticReport(
            app_version=config.app_version,
            database={
                "status": "ready" if database.ping() else "error",
                "schema_version": database.current_schema_version,
                "size_bytes": (
                    config.database_path.stat().st_size
                    if config.database_path.exists()
                    else 0
                ),
            },
            counts=repository.diagnostic_counts(),
            runtime=current_runtime_status(),
            system=inspect_system(),
            privacy={
                "memory_enabled": settings.get("privacy.memory_enabled", True),
                "proactive_enabled": settings.get(
                    "privacy.proactive_enabled",
                    True,
                ),
                "checkin_enabled": settings.get(
                    "proactive.checkin_enabled",
                    True,
                ),
                "quiet_hours": settings.get("privacy.quiet_hours"),
                "daily_checkin_limit": settings.get(
                    "proactive.daily_limit",
                    2,
                ),
                "auth_token_configured": bool(config.auth_token),
                "llm_configured": bool(config.llm_base_url),
                "embedding_configured": bool(config.embedding_base_url),
                "speech_configured": bool(config.speech_realtime_url),
                "contains_private_content": False,
            },
        )

    @app.get("/v1/models", response_model=list[ModelRecord])
    def models(_: None = Depends(authorize)) -> list[ModelRecord]:
        return [ModelRecord(**item) for item in repository.list_models()]

    @app.get("/v1/avatar/status", response_model=AvatarStatus)
    def avatar_status(_: None = Depends(authorize)) -> AvatarStatus:
        return avatar_runtime.status()

    @app.get("/v1/avatar/assets/{state}")
    def avatar_asset(
        state: str,
        token: str | None = Query(default=None),
        authorization: str | None = Header(default=None),
    ) -> FileResponse:
        if config.auth_token and not (
            authorization == f"Bearer {config.auth_token}"
            or token == config.auth_token
        ):
            raise HTTPException(status_code=401, detail="Invalid local session token")
        asset = avatar_runtime.asset_path(state)
        if asset is None:
            raise HTTPException(status_code=404, detail="Avatar state asset not found")
        return FileResponse(
            asset,
            media_type="video/mp4",
            filename=f"{avatar_runtime.character_id}-{state}.mp4",
            content_disposition_type="inline",
        )

    @app.post("/v1/avatar/state", response_model=AvatarStatus)
    async def update_avatar_state(
        value: AvatarStateUpdate,
        _: None = Depends(authorize),
    ) -> AvatarStatus:
        return await commit_avatar_state(value)

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(
        request: ChatRequest, _: None = Depends(authorize)
    ) -> ChatResponse:
        await commit_avatar_state(
            AvatarStateUpdate(
                state="thinking",
                emotion="attentive",
                intensity=0.48,
            )
        )
        try:
            return await chat_service.chat(request)
        finally:
            await commit_avatar_state(
                AvatarStateUpdate(
                    state="idle",
                    emotion="calm",
                    intensity=0.35,
                )
            )

    @app.get(
        "/v1/conversations",
        response_model=list[ConversationSummary],
    )
    def conversations(
        limit: int = Query(default=50, ge=1, le=200),
        _: None = Depends(authorize),
    ) -> list[ConversationSummary]:
        return [
            ConversationSummary(**item)
            for item in repository.list_sessions(limit)
        ]

    @app.get(
        "/v1/conversations/{session_id}/messages",
        response_model=list[dict[str, Any]],
    )
    def messages(
        session_id: str,
        limit: int = Query(default=200, ge=1, le=1_000),
        _: None = Depends(authorize),
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in repository.list_messages(session_id, limit)
        ]

    @app.post("/v1/memories", response_model=MemoryRecord, status_code=201)
    async def create_memory(
        value: MemoryCreate, _: None = Depends(authorize)
    ) -> MemoryRecord:
        memory = repository.create_memory(value)
        memory_intelligence.schedule_memory(memory.id)
        await event_hub.publish(
            EventEnvelope(
                type="memory.committed",
                payload={"memory_id": memory.id, "kind": memory.kind},
            )
        )
        return memory

    @app.post("/v1/memories/query", response_model=list[MemoryRecord])
    async def query_memories(
        value: MemoryQuery, _: None = Depends(authorize)
    ) -> list[MemoryRecord]:
        return await memory_intelligence.query(value)

    @app.get("/v1/memories/index/status", response_model=MemoryIndexStatus)
    def memory_index_status(
        _: None = Depends(authorize),
    ) -> MemoryIndexStatus:
        return memory_intelligence.status()

    @app.post(
        "/v1/memories/index/rebuild",
        response_model=MemoryIndexRebuildResponse,
        status_code=202,
    )
    async def rebuild_memory_index(
        _: None = Depends(authorize),
    ) -> MemoryIndexRebuildResponse:
        return memory_intelligence.rebuild()

    @app.get(
        "/v1/memories/{memory_id}/context",
        response_model=MemoryContext,
    )
    def memory_context(
        memory_id: str,
        _: None = Depends(authorize),
    ) -> MemoryContext:
        context = repository.get_memory_context(memory_id)
        if not context:
            raise HTTPException(status_code=404, detail="Memory not found")
        return context

    @app.patch("/v1/memories/{memory_id}", response_model=MemoryRecord)
    async def update_memory(
        memory_id: str,
        value: MemoryUpdate,
        _: None = Depends(authorize),
    ) -> MemoryRecord:
        memory = repository.update_memory(memory_id, value)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        memory_intelligence.schedule_memory(memory.id)
        await event_hub.publish(
            EventEnvelope(
                type="memory.committed",
                payload={"memory_id": memory.id, "kind": memory.kind, "updated": True},
            )
        )
        return memory

    @app.get(
        "/v1/conversation-summaries",
        response_model=ConversationSummaryList,
    )
    def conversation_summaries(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        _: None = Depends(authorize),
    ) -> ConversationSummaryList:
        items, total = repository.list_summaries(
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
        return ConversationSummaryList(items=items, total=total)

    @app.post(
        "/v1/conversations/{session_id}/summaries",
        response_model=ConversationSummaryRecord,
        status_code=202,
    )
    async def generate_conversation_summary(
        session_id: str,
        _: None = Depends(authorize),
    ) -> ConversationSummaryRecord:
        if not repository.list_messages(session_id, 1):
            raise HTTPException(status_code=404, detail="Conversation not found")
        try:
            return summary_service.schedule(session_id, force=True)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete(
        "/v1/conversation-summaries/{summary_id}",
        status_code=204,
    )
    def delete_conversation_summary(
        summary_id: str,
        _: None = Depends(authorize),
    ) -> None:
        if not repository.delete_summary(summary_id):
            raise HTTPException(status_code=404, detail="Summary not found")

    @app.delete("/v1/memories/{memory_id}", status_code=204)
    async def delete_memory(
        memory_id: str, _: None = Depends(authorize)
    ) -> None:
        if not repository.delete_memory(memory_id):
            raise HTTPException(status_code=404, detail="Memory not found")
        await event_hub.publish(
            EventEnvelope(
                type="memory.committed",
                payload={"memory_id": memory_id, "deleted": True},
            )
        )

    @app.get("/v1/plans", response_model=list[PlanRecord])
    def plans(
        include_completed: bool = True,
        _: None = Depends(authorize),
    ) -> list[PlanRecord]:
        return repository.list_plans(include_completed)

    @app.post("/v1/plans", response_model=PlanRecord, status_code=201)
    async def create_plan(
        value: PlanCreate, _: None = Depends(authorize)
    ) -> PlanRecord:
        plan = repository.create_plan(value)
        await event_hub.publish(
            EventEnvelope(type="task.created", payload={"task": plan.model_dump(mode="json")})
        )
        return plan

    @app.patch("/v1/plans/{plan_id}", response_model=PlanRecord)
    async def update_plan(
        plan_id: str,
        value: PlanUpdate,
        _: None = Depends(authorize),
    ) -> PlanRecord:
        plan = repository.update_plan(plan_id, value)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        await event_hub.publish(
            EventEnvelope(type="task.progress", payload={"task": plan.model_dump(mode="json")})
        )
        return plan

    @app.delete("/v1/plans/{plan_id}", status_code=204)
    async def delete_plan(
        plan_id: str, _: None = Depends(authorize)
    ) -> None:
        if not repository.delete_plan(plan_id):
            raise HTTPException(status_code=404, detail="Plan not found")
        await event_hub.publish(
            EventEnvelope(type="task.completed", payload={"task_id": plan_id, "deleted": True})
        )

    @app.get("/v1/notifications", response_model=list[NotificationRecord])
    def list_notifications(
        include_acknowledged: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=200),
        _: None = Depends(authorize),
    ) -> list[NotificationRecord]:
        return repository.list_notifications(
            include_acknowledged=include_acknowledged,
            limit=limit,
        )

    @app.post(
        "/v1/notifications/{notification_id}/acknowledge",
        response_model=NotificationRecord,
    )
    async def acknowledge_notification(
        notification_id: str,
        _: None = Depends(authorize),
    ) -> NotificationRecord:
        record = repository.acknowledge_notification(notification_id)
        if not record:
            raise HTTPException(status_code=404, detail="Notification not found")
        await event_hub.publish(
            EventEnvelope(
                type="notification.acknowledged",
                payload={"id": notification_id},
            )
        )
        return record

    @app.get("/v1/persona", response_model=PersonaRecord)
    def persona(_: None = Depends(authorize)) -> PersonaRecord:
        return repository.active_persona()

    @app.put("/v1/persona", response_model=PersonaRecord)
    def update_persona(
        value: PersonaUpdate, _: None = Depends(authorize)
    ) -> PersonaRecord:
        return repository.create_persona_version(value)

    @app.get("/v1/mood/current", response_model=MoodRecord)
    def mood(_: None = Depends(authorize)) -> MoodRecord:
        return repository.current_mood()

    @app.post("/v1/mood", response_model=MoodRecord)
    async def update_mood(
        value: MoodUpdate, _: None = Depends(authorize)
    ) -> MoodRecord:
        mood_record = repository.set_mood(value)
        await event_hub.publish(
            EventEnvelope(
                type="mood.changed",
                payload=mood_record.model_dump(mode="json"),
            )
        )
        return mood_record

    @app.get("/v1/settings", response_model=dict[str, Any])
    def settings(_: None = Depends(authorize)) -> dict[str, Any]:
        return repository.get_settings()

    @app.put("/v1/settings/{key}", response_model=dict[str, Any])
    def update_setting(
        key: str,
        update: SettingUpdate,
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        repository.set_setting(key, update.value)
        return {"key": key, "value": update.value}

    @app.post("/v1/voice/session", response_model=VoiceSessionResponse)
    def voice_session(_: None = Depends(authorize)) -> VoiceSessionResponse:
        speech_status = speech_runtime.status()
        return VoiceSessionResponse(
            session_id=str(uuid4()),
            status="ready" if speech_status.reachable else "degraded",
            transport="websocket",
            endpoint=speech_status.endpoint or "/v1/realtime/voice",
            provider="speech-to-speech",
            detail=(
                speech_status.detail
                if speech_status.reachable
                else f"语音契约已就绪；{speech_status.detail}。"
            ),
        )

    @app.post("/v1/voice/transcripts", response_model=MessageRecord)
    async def persist_voice_transcript(
        value: VoiceTranscriptCreate,
        _: None = Depends(authorize),
    ) -> MessageRecord:
        return await chat_service.persist_voice_transcript(value)

    @app.get("/v1/data/export", response_model=DataExport)
    def export_data(_: None = Depends(authorize)) -> DataExport:
        return repository.export_data()

    def backup_record(path) -> BackupRecord:
        stat = path.stat()
        return BackupRecord(
            name=path.name,
            created_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
            size_bytes=stat.st_size,
        )

    @app.get("/v1/data/backups", response_model=list[BackupRecord])
    def list_backups(_: None = Depends(authorize)) -> list[BackupRecord]:
        backup_directory = config.data_dir / "backups"
        if not backup_directory.exists():
            return []
        paths = sorted(
            backup_directory.glob("xinyu-backup-*.db"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return [backup_record(path) for path in paths]

    @app.post("/v1/data/backups", response_model=BackupRecord, status_code=201)
    def create_backup(_: None = Depends(authorize)) -> BackupRecord:
        return backup_record(database.backup(config.data_dir / "backups"))

    @app.post("/v1/data/import", response_model=DataImportResult)
    async def import_data(
        payload: DataImportRequest,
        _: None = Depends(authorize),
    ) -> DataImportResult:
        if not payload.confirmed:
            raise HTTPException(status_code=400, detail="Import confirmation required")
        row_count = sum(len(rows) for rows in payload.data.values())
        if row_count > 1_000_000:
            raise HTTPException(status_code=413, detail="Import contains too many rows")
        safety_path = database.backup(config.data_dir / "backups")
        try:
            imported_rows = repository.import_data(
                payload.schema_version,
                payload.data,
            )
        except sqlite3.Error as error:
            raise HTTPException(
                status_code=422,
                detail="Import violates database constraints",
            ) from error
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        result = DataImportResult(
            imported_rows=imported_rows,
            safety_backup=backup_record(safety_path),
            imported_at=datetime.now(timezone.utc),
        )
        memory_intelligence.rebuild()
        await event_hub.publish(
            EventEnvelope(
                type="runtime.ready",
                payload={"data_imported": True, "rows": imported_rows},
            )
        )
        return result

    @app.post(
        "/v1/data/backups/{backup_name}/restore",
        response_model=RestoreResult,
    )
    async def restore_backup(
        backup_name: str,
        confirmation: ConfirmAction,
        _: None = Depends(authorize),
    ) -> RestoreResult:
        if not confirmation.confirmed:
            raise HTTPException(status_code=400, detail="Restore confirmation required")
        if backup_name != backup_name.split("/")[-1] or "\\" in backup_name:
            raise HTTPException(status_code=400, detail="Invalid backup name")
        backup_directory = config.data_dir / "backups"
        source = backup_directory / backup_name
        if not source.is_file() or not backup_name.startswith("xinyu-backup-"):
            raise HTTPException(status_code=404, detail="Backup not found")
        safety_path = database.backup(
            backup_directory,
            protected=(source,),
        )
        try:
            database.restore(source)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        result = RestoreResult(
            restored_from=source.name,
            safety_backup=backup_record(safety_path),
            restored_at=datetime.now(timezone.utc),
        )
        await event_hub.publish(
            EventEnvelope(
                type="runtime.ready",
                payload={
                    "data_restored": True,
                    "restored_from": source.name,
                },
            )
        )
        return result

    @app.delete("/v1/data", status_code=204)
    async def delete_data(_: None = Depends(authorize)) -> None:
        database.backup(config.data_dir / "backups")
        repository.delete_user_data()
        await event_hub.publish(
            EventEnvelope(type="runtime.ready", payload={"data_reset": True})
        )

    @app.websocket("/v1/app/events")
    async def events(websocket: WebSocket) -> None:
        if config.auth_token:
            token = websocket.query_params.get("token")
            if token != config.auth_token:
                await websocket.close(code=4401)
                return
        await event_hub.connect(websocket)
        try:
            await websocket.send_json(
                EventEnvelope(
                    type="runtime.ready",
                    payload={"version": config.app_version},
                ).model_dump(mode="json")
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await event_hub.disconnect(websocket)

    @app.websocket("/v1/realtime/voice")
    async def realtime_voice(websocket: WebSocket) -> None:
        if config.auth_token:
            token = websocket.query_params.get("token")
            if token != config.auth_token:
                await websocket.close(code=4401)
                return
        await websocket.accept()
        speech_status = speech_runtime.status()
        if speech_status.reachable and speech_status.endpoint:
            await websocket.send_json(
                EventEnvelope(
                    type="voice.session.ready",
                    payload={
                        "status": "ready",
                        "provider": "speech-to-speech",
                        "missing_components": [],
                        "detail": "已连接独立 speech-to-speech Realtime 进程。",
                    },
                ).model_dump(mode="json")
            )
            try:
                async with websocket_connect(
                    speech_status.endpoint,
                    max_size=None,
                ) as upstream:
                    await relay_voice_messages(websocket, upstream)
            except WebSocketDisconnect:
                return
            except Exception as error:
                try:
                    await websocket.send_json(
                        EventEnvelope(
                            type="error",
                            payload={
                                "code": "voice_upstream_disconnected",
                                "recoverable": True,
                                "detail": "语音运行时连接已中断，可继续使用文字对话。",
                                "error_type": type(error).__name__,
                            },
                        ).model_dump(mode="json")
                    )
                except Exception:
                    pass
            return

        await websocket.send_json(
            EventEnvelope(
                type="voice.session.ready",
                payload={
                    "status": "degraded",
                    "provider": "speech-to-speech",
                    "missing_components": ["stt", "tts"],
                    "detail": "语音网关可连接，但本机语音模型尚未安装。",
                },
            ).model_dump(mode="json")
        )
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                await websocket.send_json(
                    EventEnvelope(
                        type="error",
                        payload={
                            "code": "voice_runtime_unavailable",
                            "recoverable": True,
                            "detail": "请先在模型管理中安装并启用 STT 与 TTS。",
                        },
                    ).model_dump(mode="json")
                )
        except WebSocketDisconnect:
            return

    return app
