import asyncio
import sqlite3
from pathlib import Path

from xinyu_core.contracts import MemoryCreate, MemoryQuery
from xinyu_core.database import Database
from xinyu_core.embeddings import EmbeddingProvider
from xinyu_core.memory_intelligence import MemoryIntelligenceService
from xinyu_core.repository import Repository
from xinyu_core.summaries import (
    ConversationSummaryService,
    DisabledSummaryProvider,
    SummaryProvider,
)


def make_repository(tmp_path: Path) -> Repository:
    database = Database(tmp_path / "xinyu.db")
    database.initialize()
    return Repository(database)


class DeterministicEmbeddingProvider(EmbeddingProvider):
    id = "deterministic-test"
    model = "test-embedding-512"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 512
            if "咖啡" in text or "拿铁" in text:
                vector[0] = 1.0
            elif "散步" in text or "走路" in text:
                vector[1] = 1.0
            else:
                vector[2] = 1.0
            vectors.append(vector)
        return vectors


class FailingEmbeddingProvider(DeterministicEmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("service_unavailable")


class DeterministicSummaryProvider(SummaryProvider):
    id = "deterministic-summary"
    model = "summary-test"

    async def summarize(self, messages, previous_summary):
        prefix = f"{previous_summary}；" if previous_summary else ""
        return f"{prefix}覆盖 {len(messages)} 条消息"


def add_messages(repository: Repository, session_id: str, count: int) -> None:
    repository.ensure_session(session_id, "text")
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        repository.add_message(session_id, role, f"消息 {index + 1}")


def test_schema_v2_exports_summaries_but_not_vectors(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    add_messages(repository, "session-export", 24)
    messages = repository.summary_messages("session-export")
    summary = repository.create_summary_job(
        "session-export", messages, "test", "test-model"
    )
    repository.complete_summary(summary.id, "用户可见摘要")

    exported = repository.export_data()

    assert exported.schema_version == 2
    assert exported.data["conversation_summaries"][0]["content"] == "用户可见摘要"
    assert "memory_embeddings" not in exported.data
    assert "memory_vectors" not in exported.data


def test_semantic_index_filters_sensitive_and_degrades_to_fts(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    coffee = repository.create_memory(
        MemoryCreate(kind="preference", title="饮品", content="喜欢少糖拿铁")
    )
    repository.create_memory(
        MemoryCreate(
            kind="profile",
            title="私密资料",
            content="咖啡店暗号",
            sensitivity="sensitive",
        )
    )
    service = MemoryIntelligenceService(repository, DeterministicEmbeddingProvider())
    asyncio.run(service.index_memory(coffee.id))

    semantic = asyncio.run(service.query(MemoryQuery(query="咖啡", limit=5)))
    assert [item.id for item in semantic] == [coffee.id]
    assert service.status().indexed_count == 1

    degraded = MemoryIntelligenceService(repository, FailingEmbeddingProvider())
    lexical = asyncio.run(degraded.query(MemoryQuery(query="拿铁", limit=5)))
    assert [item.id for item in lexical] == [coffee.id]
    assert degraded.status().status == "degraded"


def test_summary_threshold_delete_tombstone_and_manual_rebuild(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    add_messages(repository, "session-summary", 24)
    service = ConversationSummaryService(repository, DeterministicSummaryProvider())

    async def exercise() -> None:
        first = service.maybe_schedule("session-summary")
        assert first is not None
        await service.close()
        active = repository.active_summary("session-summary")
        assert active is not None
        assert active.message_count == 12

        assert repository.delete_summary(active.id) is True
        assert repository.active_summary("session-summary") is None
        assert repository.list_summaries()[0] == []
        assert service.maybe_schedule("session-summary") is None

        rebuilt = service.schedule("session-summary", force=True)
        await service.close()
        assert repository.summary_job(rebuilt.id).status == "ready"

    asyncio.run(exercise())


def test_unconfigured_summary_is_honest_and_pending_jobs_recover(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    add_messages(repository, "session-disabled", 24)
    disabled = ConversationSummaryService(
        repository, DisabledSummaryProvider("local-companion")
    )
    record = disabled.schedule("session-disabled", force=True)
    assert record.status == "unavailable"
    assert record.error_code == "llm_not_configured"

    pending = repository.create_summary_job(
        "session-disabled",
        repository.summary_messages("session-disabled"),
        "test",
        "test",
    )
    disabled.recover_pending()
    recovered = repository.summary_job(pending.id)
    assert recovered.status == "failed"
    assert recovered.error_code == "process_restarted"


def test_v1_export_import_upgrades_without_vectors_or_summaries(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "source")
    memory = source.create_memory(
        MemoryCreate(kind="preference", title="饮品", content="喜欢乌龙茶")
    )
    exported = source.export_data()
    v1_data = {
        key: value
        for key, value in exported.data.items()
        if key != "conversation_summaries"
    }

    target = make_repository(tmp_path / "target")
    imported = target.import_data(1, v1_data)

    assert imported == sum(len(rows) for rows in v1_data.values() if rows is not v1_data["model_registry"])
    assert target.get_memory(memory.id).content == "喜欢乌龙茶"
    assert target.list_summaries() == ([], 0)
    assert target.memory_index_status("test-model")["pending_count"] == 1


def test_database_still_initializes_when_vector_extension_cannot_load(
    tmp_path: Path, monkeypatch
) -> None:
    import xinyu_core.database as database_module

    class BrokenSqliteVec:
        @staticmethod
        def load(connection) -> None:
            raise sqlite3.OperationalError("extension unavailable")

    monkeypatch.setattr(database_module, "sqlite_vec", BrokenSqliteVec())
    database = Database(tmp_path / "fallback.db")
    database.initialize()
    repository = Repository(database)
    repository.create_memory(
        MemoryCreate(kind="preference", title="饮品", content="喜欢绿茶")
    )
    assert repository.query_memories(MemoryQuery(query="绿茶"))[0].title == "饮品"
