from datetime import datetime, timedelta, timezone
from pathlib import Path

from xinyu_core.contracts import MemoryCreate, MemoryQuery, MemoryUpdate, PlanCreate
from xinyu_core.database import Database
from xinyu_core.repository import Repository


def make_repository(tmp_path: Path) -> Repository:
    database = Database(tmp_path / "xinyu.db")
    database.initialize()
    return Repository(database)


def test_memory_round_trip_and_soft_delete(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    memory = repository.create_memory(
        MemoryCreate(
            kind="preference",
            title="喜欢的饮料",
            content="下午喜欢少糖拿铁",
            user_confirmed=True,
        )
    )

    results = repository.query_memories(MemoryQuery(query="拿铁"))
    assert [item.id for item in results] == [memory.id]

    updated = repository.update_memory(
        memory.id, MemoryUpdate(content="下午喜欢无糖拿铁", starred=True)
    )
    assert updated is not None
    assert updated.content == "下午喜欢无糖拿铁"
    assert updated.starred is True

    assert repository.delete_memory(memory.id) is True
    assert repository.query_memories(MemoryQuery(query="拿铁")) == []


def test_plan_and_export(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    plan = repository.create_plan(PlanCreate(title="晚上散步"))

    assert repository.list_plans()[0].id == plan.id
    export = repository.export_data()
    assert export.schema_version == 2
    assert any(item["id"] == plan.id for item in export.data["tasks"])


def test_database_backup_is_a_readable_snapshot(tmp_path: Path) -> None:
    database = Database(tmp_path / "source.db")
    database.initialize()
    repository = Repository(database)
    repository.create_plan(PlanCreate(title="写进备份"))

    backup_path = database.backup(tmp_path / "backups")
    restored = Repository(Database(backup_path))

    assert restored.list_plans()[0].title == "写进备份"


def test_memory_conflicts_create_a_traceable_supersession(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    first = repository.create_memory(
        MemoryCreate(
            kind="profile",
            title="你的生日",
            content="7月20日",
            user_confirmed=True,
        )
    )
    duplicate = repository.create_memory(
        MemoryCreate(
            kind="profile",
            title="你的生日",
            content="7月20日",
            user_confirmed=True,
        )
    )
    second = repository.create_memory(
        MemoryCreate(
            kind="profile",
            title="你的生日",
            content="7月21日",
            user_confirmed=True,
        )
    )

    assert duplicate.id == first.id
    assert second.supersedes_id == first.id
    assert [item.content for item in repository.query_memories(MemoryQuery())] == [
        "7月21日"
    ]
    exported = repository.export_data().data
    old = next(item for item in exported["memories"] if item["id"] == first.id)
    assert old["valid_to"] is not None
    assert exported["memory_edges"][0]["relation"] == "supersedes"


def test_only_unconfirmed_inferred_memories_expire(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    inferred = repository.create_memory(
        MemoryCreate(
            kind="concern",
            title="可能的担心",
            content="临时推断",
            source="system_inference",
        )
    )
    explicit = repository.create_memory(
        MemoryCreate(
            kind="concern",
            title="明确在意",
            content="用户明确表达",
            source="user_explicit",
            user_confirmed=True,
        )
    )

    expired = repository.expire_stale_memories(
        datetime.now(timezone.utc) + timedelta(minutes=1)
    )

    assert expired == 1
    active_ids = {
        item.id for item in repository.query_memories(MemoryQuery())
    }
    assert inferred.id not in active_ids
    assert explicit.id in active_ids
