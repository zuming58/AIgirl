from __future__ import annotations

import asyncio
import hashlib

from .contracts import MemoryIndexRebuildResponse, MemoryIndexStatus, MemoryQuery, MemoryRecord
from .embeddings import EmbeddingProvider
from .repository import Repository


def _memory_text(memory: MemoryRecord) -> str:
    return f"{memory.kind}\n{memory.title}\n{memory.content}"


class MemoryIntelligenceService:
    def __init__(self, repository: Repository, provider: EmbeddingProvider) -> None:
        self.repository = repository
        self.provider = provider
        self._tasks: set[asyncio.Task[None]] = set()
        self._rebuild_task: asyncio.Task[None] | None = None

    def status(self) -> MemoryIndexStatus:
        state = self.repository.memory_index_status(self.provider.model)
        if not self.provider.configured:
            state["status"] = "disabled"
            state["last_error"] = "embedding_not_configured"
        return MemoryIndexStatus(**state)

    async def query(self, value: MemoryQuery) -> list[MemoryRecord]:
        lexical_value = value.model_copy(update={"limit": min(200, max(value.limit * 4, 20))})
        lexical = self.repository.query_memories(lexical_value)
        if not value.query.strip() or not self.provider.configured:
            return lexical[: value.limit]
        try:
            vector = (await self.provider.embed([value.query.strip()]))[0]
            semantic = self.repository.memory_vector_search(
                vector,
                value,
                min(200, max(value.limit * 4, 20)),
            )
        except Exception as error:
            self.repository.set_memory_index_state(
                "degraded",
                self.provider.model,
                last_error=type(error).__name__,
            )
            return lexical[: value.limit]

        candidates = {item.id: item for item in [*lexical, *semantic]}
        scores: dict[str, float] = {memory_id: 0 for memory_id in candidates}
        for rank, item in enumerate(lexical, start=1):
            scores[item.id] += 0.65 / (60 + rank)
        for rank, item in enumerate(semantic, start=1):
            scores[item.id] += 0.35 / (60 + rank)
        for item in candidates.values():
            scores[item.id] += item.salience * 0.0001
            if item.starred:
                scores[item.id] += 0.0002
        ranked = sorted(candidates.values(), key=lambda item: scores[item.id], reverse=True)
        return ranked[: value.limit]

    def schedule_memory(self, memory_id: str) -> None:
        if not self.provider.configured:
            return
        task = asyncio.create_task(self.index_memory(memory_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def index_memory(self, memory_id: str) -> None:
        memory = self.repository.get_memory(memory_id)
        if not memory:
            return
        try:
            text = _memory_text(memory)
            vector = (await self.provider.embed([text]))[0]
            self.repository.save_memory_embedding(
                memory.id,
                hashlib.sha256(text.encode("utf-8")).hexdigest(),
                self.provider.model,
                vector,
            )
            self.repository.set_memory_index_state(
                "ready",
                self.provider.model,
                dimensions=len(vector),
            )
        except Exception as error:
            self.repository.set_memory_index_state(
                "degraded",
                self.provider.model,
                last_error=type(error).__name__,
            )

    def rebuild(self) -> MemoryIndexRebuildResponse:
        status = self.status()
        if not self.provider.configured:
            return MemoryIndexRebuildResponse(
                status="disabled",
                pending_count=status.pending_count,
            )
        if self._rebuild_task and not self._rebuild_task.done():
            return MemoryIndexRebuildResponse(
                status="building",
                pending_count=status.pending_count,
            )
        self.repository.set_memory_index_state("building", self.provider.model)
        self._rebuild_task = asyncio.create_task(self._run_rebuild())
        self._tasks.add(self._rebuild_task)
        self._rebuild_task.add_done_callback(self._tasks.discard)
        return MemoryIndexRebuildResponse(
            status="building",
            pending_count=status.pending_count,
        )

    async def _run_rebuild(self) -> None:
        self.repository.clear_memory_embeddings()
        memories = self.repository.active_memories_for_index()
        try:
            for start in range(0, len(memories), 32):
                batch = memories[start : start + 32]
                texts = [_memory_text(item) for item in batch]
                vectors = await self.provider.embed(texts)
                for memory, text, vector in zip(batch, texts, vectors, strict=True):
                    self.repository.save_memory_embedding(
                        memory.id,
                        hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        self.provider.model,
                        vector,
                    )
            self.repository.set_memory_index_state(
                "ready",
                self.provider.model,
                dimensions=512,
            )
        except Exception as error:
            self.repository.set_memory_index_state(
                "degraded",
                self.provider.model,
                last_error=type(error).__name__,
            )

    async def close(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
