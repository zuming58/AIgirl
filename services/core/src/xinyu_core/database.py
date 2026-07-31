from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            migration_directory = Path(__file__).parent / "migrations"
            for migration_path in sorted(migration_directory.glob("*.sql")):
                version = int(migration_path.stem.split("_", maxsplit=1)[0])
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?",
                    (version,),
                ).fetchone()
                if applied:
                    continue
                connection.executescript(
                    migration_path.read_text(encoding="utf-8")
                )
                connection.execute(
                    """
                    INSERT INTO schema_migrations(version, applied_at)
                    VALUES(?, ?)
                    """,
                    (version, iso_now()),
                )
            self._seed(connection)
            connection.execute(
                """
                DELETE FROM proactive_events
                WHERE event_type='plan.reminder_due'
                  AND NOT EXISTS (
                    SELECT 1 FROM tasks WHERE tasks.id=proactive_events.reason
                  )
                """
            )

    def backup(
        self,
        backup_directory: Path,
        keep: int = 10,
        protected: tuple[Path, ...] = (),
    ) -> Path:
        backup_directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = backup_directory / f"xinyu-backup-{stamp}.db"
        with self.connect() as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
        backups = sorted(
            backup_directory.glob("xinyu-backup-*.db"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        retained = {destination.resolve()}
        retained.update(path.resolve() for path in protected)
        for candidate in backups:
            if len(retained) < max(1, keep):
                retained.add(candidate.resolve())
            elif candidate.resolve() not in retained:
                candidate.unlink(missing_ok=True)
        return destination

    def restore(self, source_path: Path) -> None:
        with sqlite3.connect(source_path) as source:
            if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Backup database failed integrity validation")
            tables = {
                row[0]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {"schema_migrations", "personas", "sessions", "tasks"}
            if not required.issubset(tables):
                raise ValueError("Backup database does not match the Xinyu schema")
            version = source.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if version > self.current_schema_version:
                raise ValueError("Backup schema is newer than this application")
            with sqlite3.connect(self.path) as target:
                source.backup(target)
        self.initialize()

    @property
    def current_schema_version(self) -> int:
        versions = [
            int(path.stem.split("_", maxsplit=1)[0])
            for path in (Path(__file__).parent / "migrations").glob("*.sql")
        ]
        return max(versions, default=0)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ping(self) -> bool:
        try:
            with self.connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def _seed(self, connection: sqlite3.Connection) -> None:
        now = iso_now()
        if connection.execute("SELECT COUNT(*) FROM personas").fetchone()[0] == 0:
            connection.execute(
                """
                INSERT INTO personas(
                    id, version, name, relationship_role, background,
                    voice_json, behavior_json, boundaries_json, active, created_at
                ) VALUES(?, 1, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    "persona-default",
                    "心屿",
                    "companion",
                    "温暖、尊重边界、记得共同经历的本地陪伴式智能体。",
                    json.dumps({"pace": "gentle", "style": "warm"}, ensure_ascii=False),
                    json.dumps(
                        {"verbosity": "short", "humor": "light", "initiative": "medium"},
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {"quiet_hours": "23:30-08:00", "memory_control": "user"},
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )
        if connection.execute("SELECT COUNT(*) FROM mood_states").fetchone()[0] == 0:
            connection.execute(
                """
                INSERT INTO mood_states(
                    id, valence, arousal, energy, closeness, stress, reason, created_at
                ) VALUES(?, 0.45, 0.25, 0.55, 0.62, 0.08, 'initial', ?)
                """,
                ("mood-initial", now),
            )
        models = [
            ("core-local", "core", "xinyu", "ready", 1, {"version": "0.1.0"}),
            ("llm-local", "llm", "fallback", "degraded", 1, {"configured": False}),
            ("stt-local", "stt", "speech-to-speech", "unavailable", 1, {}),
            ("tts-local", "tts", "speech-to-speech", "unavailable", 1, {}),
            (
                "avatar-local",
                "avatar",
                "prerendered",
                "degraded",
                0,
                {"fallback": "static-hero"},
            ),
        ]
        for model in models:
            connection.execute(
                """
                INSERT OR IGNORE INTO model_registry(
                    id, kind, provider, status, required, metadata_json, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model[0],
                    model[1],
                    model[2],
                    model[3],
                    model[4],
                    json.dumps(model[5], ensure_ascii=False),
                    now,
                ),
            )
        defaults: dict[str, Any] = {
            "privacy.memory_enabled": True,
            "privacy.proactive_enabled": True,
            "privacy.quiet_hours": "23:30-08:00",
            "proactive.checkin_enabled": True,
            "proactive.daily_limit": 2,
            "proactive.cooldown_minutes": 240,
            "proactive.inactivity_minutes": 240,
            "voice.enabled": False,
            "voice.input_device_id": "",
            "avatar.quality": "high",
        }
        for key, value in defaults.items():
            connection.execute(
                "INSERT OR IGNORE INTO settings(key, value_json, updated_at) VALUES(?, ?, ?)",
                (key, json.dumps(value, ensure_ascii=False), now),
            )
