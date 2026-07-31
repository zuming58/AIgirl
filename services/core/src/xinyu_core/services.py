from __future__ import annotations

import re
from uuid import uuid4

from .contracts import (
    ChatRequest,
    ChatResponse,
    EventEnvelope,
    MemoryCreate,
    MemoryQuery,
    MessageRecord,
    VoiceTranscriptCreate,
)
from .events import EventHub
from .providers import ChatProvider, DevelopmentCompanionProvider
from .repository import Repository


class MemoryCandidateExtractor:
    explicit_patterns = (
        (re.compile(r"(?:请)?记住[：,:， ]*(.{2,80})"), "profile", "你让我记住的事"),
        (re.compile(r"我喜欢[：,:， ]*(.{1,60})"), "preference", "你的偏好"),
        (re.compile(r"我不喜欢[：,:， ]*(.{1,60})"), "preference", "你不喜欢的事"),
        (re.compile(r"我的生日是[：,:， ]*(.{2,30})"), "profile", "你的生日"),
    )

    def extract(self, text: str, source_message_id: str) -> list[MemoryCreate]:
        candidates: list[MemoryCreate] = []
        for pattern, kind, title in self.explicit_patterns:
            match = pattern.search(text)
            if not match:
                continue
            content = match.group(1).strip("。.!！?？ ")
            if content:
                candidates.append(
                    MemoryCreate(
                        kind=kind,
                        title=title,
                        content=content,
                        source="user_explicit",
                        source_message_id=source_message_id,
                        confidence=0.98,
                        salience=0.7,
                        user_confirmed=True,
                    )
                )
                break
        return candidates


class ChatService:
    def __init__(
        self,
        repository: Repository,
        provider: ChatProvider,
        events: EventHub,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.events = events
        self.extractor = MemoryCandidateExtractor()

    async def persist_voice_transcript(
        self,
        value: VoiceTranscriptCreate,
    ) -> MessageRecord:
        session_id = self.repository.ensure_session(value.session_id, "voice")
        existing = self.repository.find_voice_transcript(
            session_id,
            value.transcript_id,
        )
        if existing:
            return existing

        message = self.repository.add_message(
            session_id,
            value.role,
            value.content,
            {
                **value.metadata,
                "channel": "voice",
                "voice_transcript_id": value.transcript_id,
            },
        )
        await self.events.publish(
            EventEnvelope(
                type="transcript.persisted",
                session_id=session_id,
                payload={
                    "message_id": message.id,
                    "role": message.role,
                    "transcript_id": value.transcript_id,
                },
            )
        )

        memory_enabled = self.repository.get_settings().get(
            "privacy.memory_enabled",
            True,
        )
        if value.role == "user" and memory_enabled:
            for candidate in self.extractor.extract(value.content, message.id):
                memory = self.repository.create_memory(candidate)
                await self.events.publish(
                    EventEnvelope(
                        type="memory.committed",
                        session_id=session_id,
                        payload={
                            "memory_id": memory.id,
                            "kind": memory.kind,
                            "channel": "voice",
                        },
                    )
                )
        return message

    async def chat(self, request: ChatRequest) -> ChatResponse:
        session_id = self.repository.ensure_session(request.session_id, request.channel)
        trace_id = str(uuid4())
        turn_id = self.repository.create_turn(session_id, trace_id, request.channel)
        user_message = self.repository.add_message(
            session_id, "user", request.message, request.metadata
        )
        await self.events.publish(
            EventEnvelope(
                type="transcript.final",
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                payload={"text": request.message, "channel": request.channel},
            )
        )
        history = self.repository.list_messages(session_id, 24)
        memories = self.repository.query_memories(
            MemoryQuery(query=request.message, limit=5)
        )
        persona = self.repository.active_persona()
        provider_id = self.provider.id
        try:
            reply = await self.provider.reply(
                request.message,
                history[:-1],
                persona,
                [memory.content for memory in memories],
            )
        except Exception as provider_error:
            if isinstance(self.provider, DevelopmentCompanionProvider):
                self.repository.fail_turn(turn_id)
                raise
            fallback = DevelopmentCompanionProvider()
            reply = await fallback.reply(
                request.message,
                history[:-1],
                persona,
                [memory.content for memory in memories],
            )
            provider_id = fallback.id
            self.repository.set_model_status(
                "llm-local",
                self.provider.id,
                "degraded",
                {
                    "configured": True,
                    "last_error": type(provider_error).__name__,
                    "fallback": fallback.id,
                },
            )
            await self.events.publish(
                EventEnvelope(
                    type="runtime.degraded",
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    payload={
                        "component": "llm",
                        "fallback": fallback.id,
                        "reason": type(provider_error).__name__,
                    },
                )
            )
        assistant_message = self.repository.add_message(
            session_id,
            "assistant",
            reply,
            {"provider": provider_id, "turn_id": turn_id},
        )
        candidate_ids: list[str] = []
        memory_enabled = self.repository.get_settings().get(
            "privacy.memory_enabled", True
        )
        if memory_enabled:
            for candidate in self.extractor.extract(
                request.message, user_message.id
            ):
                memory = self.repository.create_memory(candidate)
                candidate_ids.append(memory.id)
                await self.events.publish(
                    EventEnvelope(
                        type="memory.committed",
                        session_id=session_id,
                        turn_id=turn_id,
                        trace_id=trace_id,
                        payload={"memory_id": memory.id, "kind": memory.kind},
                    )
                )
        self.repository.complete_turn(turn_id)
        await self.events.publish(
            EventEnvelope(
                type="assistant.text.delta",
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                payload={"text": reply, "final": True},
            )
        )
        return ChatResponse(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            reply=reply,
            provider=provider_id,
            user_message=user_message,
            assistant_message=assistant_message,
            memory_candidates=candidate_ids,
        )
