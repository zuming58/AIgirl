from __future__ import annotations

import json
import sqlite3
from array import array
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .contracts import (
    ConversationSummaryRecord,
    DataExport,
    MemoryCreate,
    MemoryContext,
    MemoryQuery,
    MemoryRecord,
    MemoryUpdate,
    MessageRecord,
    MoodRecord,
    MoodUpdate,
    NotificationRecord,
    PersonaRecord,
    PersonaUpdate,
    PlanCreate,
    PlanRecord,
    PlanUpdate,
    utc_now,
)
from .database import Database, iso_now


def _json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


class Repository:
    export_tables = (
        "personas",
        "sessions",
        "messages",
        "turns",
        "memories",
        "memory_edges",
        "conversation_summaries",
        "mood_states",
        "tasks",
        "commitments",
        "tool_runs",
        "proactive_events",
        "media_assets",
        "settings",
        "model_registry",
    )

    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_session(self, session_id: str | None, channel: str) -> str:
        session_id = session_id or str(uuid4())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO sessions(
                    id, channel, status, started_at, metadata_json
                ) VALUES(?, ?, 'active', ?, '{}')
                """,
                (session_id, channel, iso_now()),
            )
        return session_id

    def create_turn(self, session_id: str, trace_id: str, channel: str) -> str:
        turn_id = str(uuid4())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO turns(id, session_id, trace_id, channel, status, started_at)
                VALUES(?, ?, ?, ?, 'running', ?)
                """,
                (turn_id, session_id, trace_id, channel, iso_now()),
            )
        return turn_id

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    sessions.id,
                    sessions.channel,
                    sessions.status,
                    sessions.started_at,
                    COALESCE(MAX(messages.created_at), sessions.started_at)
                        AS last_active_at,
                    COUNT(messages.id) AS message_count,
                    COALESCE(
                        (
                            SELECT content
                            FROM messages AS latest
                            WHERE latest.session_id = sessions.id
                            ORDER BY latest.created_at DESC, latest.rowid DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS last_message
                FROM sessions
                LEFT JOIN messages ON messages.session_id = sessions.id
                GROUP BY sessions.id
                ORDER BY last_active_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def complete_turn(self, turn_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE turns SET status='completed', completed_at=? WHERE id=?",
                (iso_now(), turn_id),
            )

    def fail_turn(self, turn_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE turns SET status='failed', completed_at=? WHERE id=?",
                (iso_now(), turn_id),
            )

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MessageRecord:
        record = MessageRecord(
            id=str(uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            created_at=utc_now(),
            metadata=metadata or {},
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages(
                    id, session_id, role, content, created_at, metadata_json
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.session_id,
                    record.role,
                    record.content,
                    record.created_at.isoformat(),
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )
        return record

    def find_voice_transcript(
        self,
        session_id: str,
        transcript_id: str,
    ) -> MessageRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM messages
                WHERE session_id=?
                  AND json_extract(metadata_json, '$.voice_transcript_id')=?
                LIMIT 1
                """,
                (session_id, transcript_id),
            ).fetchone()
        if not row:
            return None
        return MessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            metadata=_json(row["metadata_json"], {}),
        )

    def list_messages(self, session_id: str, limit: int = 200) -> list[MessageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT rowid AS message_rowid, * FROM messages
                    WHERE session_id=?
                    ORDER BY created_at DESC, rowid DESC LIMIT ?
                )
                ORDER BY created_at ASC, message_rowid ASC
                """,
                (session_id, limit),
            ).fetchall()
        return [
            MessageRecord(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
                metadata=_json(row["metadata_json"], {}),
            )
            for row in rows
        ]

    def create_memory(self, value: MemoryCreate) -> MemoryRecord:
        memory_id = str(uuid4())
        now = utc_now()
        superseded: MemoryRecord | None = None
        generic_titles = {
            "你的偏好",
            "你不喜欢的事",
            "你让我记住的事",
        }
        with self.database.connect() as connection:
            duplicate = connection.execute(
                """
                SELECT * FROM memories
                WHERE kind=? AND title=? AND content=?
                  AND deleted_at IS NULL AND valid_to IS NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (value.kind, value.title, value.content),
            ).fetchone()
            if duplicate:
                return self._memory_from_row(duplicate)
            if value.title not in generic_titles:
                existing = connection.execute(
                    """
                    SELECT * FROM memories
                    WHERE kind=? AND title=?
                      AND deleted_at IS NULL AND valid_to IS NULL
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (value.kind, value.title),
                ).fetchone()
                if existing:
                    superseded = self._memory_from_row(existing)

        record = MemoryRecord(
            id=memory_id,
            created_at=now,
            updated_at=now,
            valid_from=now,
            supersedes_id=superseded.id if superseded else None,
            **value.model_dump(),
        )
        with self.database.connect() as connection:
            if superseded:
                connection.execute(
                    """
                    UPDATE memories
                    SET valid_to=?, updated_at=?
                    WHERE id=? AND valid_to IS NULL
                    """,
                    (now.isoformat(), now.isoformat(), superseded.id),
                )
                connection.execute(
                    "DELETE FROM memory_search WHERE memory_id=?",
                    (superseded.id,),
                )
                self._remove_memory_embedding(connection, superseded.id)
            connection.execute(
                """
                INSERT INTO memories(
                    id, kind, title, content, source, source_message_id,
                    confidence, salience, user_confirmed, sensitivity, starred,
                    valid_from, supersedes_id, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.kind,
                    record.title,
                    record.content,
                    record.source,
                    record.source_message_id,
                    record.confidence,
                    record.salience,
                    int(record.user_confirmed),
                    record.sensitivity,
                    int(record.starred),
                    record.valid_from.isoformat(),
                    record.supersedes_id,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            if superseded:
                connection.execute(
                    """
                    INSERT INTO memory_edges(
                        id, from_memory_id, to_memory_id, relation, weight, created_at
                    ) VALUES(?, ?, ?, 'supersedes', 1, ?)
                    """,
                    (
                        str(uuid4()),
                        record.id,
                        superseded.id,
                        now.isoformat(),
                    ),
                )
            self._index_memory(connection, record.id, record.kind, record.title, record.content)
        return record

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id=? AND deleted_at IS NULL",
                (memory_id,),
            ).fetchone()
        return self._memory_from_row(row) if row else None

    def get_memory_context(self, memory_id: str) -> MemoryContext | None:
        memory = self.get_memory(memory_id)
        if not memory:
            return None
        source_message = None
        superseded_memory = None
        with self.database.connect() as connection:
            if memory.source_message_id:
                row = connection.execute(
                    "SELECT * FROM messages WHERE id=?",
                    (memory.source_message_id,),
                ).fetchone()
                if row:
                    source_message = MessageRecord(
                        id=row["id"],
                        session_id=row["session_id"],
                        role=row["role"],
                        content=row["content"],
                        created_at=row["created_at"],
                        metadata=_json(row["metadata_json"], {}),
                    )
            if memory.supersedes_id:
                row = connection.execute(
                    "SELECT * FROM memories WHERE id=?",
                    (memory.supersedes_id,),
                ).fetchone()
                if row:
                    superseded_memory = self._memory_from_row(row)
        explanations = {
            "user_explicit": "你在对话中明确希望我记住，因此保存在本机。",
            "tool_result": "来自你授权使用的本地工具结果。",
            "system_inference": "由本地记忆整理生成，未经确认会自动过期。",
        }
        return MemoryContext(
            memory_id=memory.id,
            explanation=explanations[memory.source],
            source_message=source_message,
            superseded_memory=superseded_memory,
        )

    def query_memories(self, query: MemoryQuery) -> list[MemoryRecord]:
        conditions = ["m.deleted_at IS NULL", "m.valid_to IS NULL"]
        params: list[Any] = []
        join = ""
        if query.query.strip():
            join = "JOIN memory_search s ON s.memory_id = m.id"
            conditions.append("memory_search MATCH ?")
            tokens = [
                token.replace('"', "")
                for token in query.query.strip().split()
                if token.replace('"', "")
            ]
            params.append(" OR ".join(f'"{token}"*' for token in tokens) or '""')
        if query.kinds:
            placeholders = ",".join("?" for _ in query.kinds)
            conditions.append(f"m.kind IN ({placeholders})")
            params.extend(query.kinds)
        if query.starred_only:
            conditions.append("m.starred=1")
        if not query.include_sensitive:
            conditions.append("m.sensitivity='normal'")
        params.append(query.limit)
        sql = f"""
            SELECT m.* FROM memories m {join}
            WHERE {' AND '.join(conditions)}
            ORDER BY m.starred DESC, m.salience DESC, m.updated_at DESC
            LIMIT ?
        """
        with self.database.connect() as connection:
            try:
                rows = connection.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                if not query.query.strip():
                    raise
                rows = []
            if query.query.strip() and not rows:
                fallback = query.query.strip().lower()
                fallback_conditions = [
                    "deleted_at IS NULL",
                    "valid_to IS NULL",
                    "(lower(title) LIKE ? OR lower(content) LIKE ?)",
                ]
                fallback_params: list[Any] = [
                    f"%{fallback}%",
                    f"%{fallback}%",
                ]
                if query.kinds:
                    placeholders = ",".join("?" for _ in query.kinds)
                    fallback_conditions.append(f"kind IN ({placeholders})")
                    fallback_params.extend(query.kinds)
                if query.starred_only:
                    fallback_conditions.append("starred=1")
                if not query.include_sensitive:
                    fallback_conditions.append("sensitivity='normal'")
                fallback_params.append(query.limit)
                rows = connection.execute(
                    f"""
                    SELECT * FROM memories
                    WHERE {' AND '.join(fallback_conditions)}
                    ORDER BY starred DESC, salience DESC, updated_at DESC
                    LIMIT ?
                    """,
                    fallback_params,
                ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def update_memory(self, memory_id: str, value: MemoryUpdate) -> MemoryRecord | None:
        current = self.get_memory(memory_id)
        if not current:
            return None
        changes = value.model_dump(exclude_none=True)
        if not changes:
            return current
        allowed = {
            "title",
            "content",
            "confidence",
            "salience",
            "user_confirmed",
            "sensitivity",
            "starred",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for key, item in changes.items():
            if key not in allowed:
                continue
            assignments.append(f"{key}=?")
            params.append(int(item) if isinstance(item, bool) else item)
        assignments.append("updated_at=?")
        params.append(iso_now())
        params.append(memory_id)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE memories SET {', '.join(assignments)} WHERE id=?",
                params,
            )
            updated = connection.execute(
                "SELECT * FROM memories WHERE id=?",
                (memory_id,),
            ).fetchone()
            self._index_memory(
                connection,
                memory_id,
                updated["kind"],
                updated["title"],
                updated["content"],
            )
            self._remove_memory_embedding(connection, memory_id)
        return self._memory_from_row(updated)

    def delete_memory(self, memory_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE memories SET deleted_at=?, valid_to=? WHERE id=? AND deleted_at IS NULL",
                (iso_now(), iso_now(), memory_id),
            )
            connection.execute("DELETE FROM memory_search WHERE memory_id=?", (memory_id,))
            self._remove_memory_embedding(connection, memory_id)
        return cursor.rowcount > 0

    def expire_stale_memories(
        self,
        before: datetime | None = None,
    ) -> int:
        cutoff = before or datetime.now(timezone.utc) - timedelta(days=180)
        now = iso_now()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id FROM memories
                WHERE source='system_inference'
                  AND user_confirmed=0
                  AND starred=0
                  AND kind IN ('concern', 'episode')
                  AND updated_at < ?
                  AND deleted_at IS NULL
                  AND valid_to IS NULL
                """,
                (cutoff.isoformat(),),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                placeholders = ", ".join("?" for _ in ids)
                connection.execute(
                    f"""
                    UPDATE memories
                    SET valid_to=?, updated_at=?
                    WHERE id IN ({placeholders})
                    """,
                    [now, now, *ids],
                )
                connection.executemany(
                    "DELETE FROM memory_search WHERE memory_id=?",
                    [(memory_id,) for memory_id in ids],
                )
                for memory_id in ids:
                    self._remove_memory_embedding(connection, memory_id)
        return len(ids)

    def active_memories_for_index(self) -> list[MemoryRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memories
                WHERE deleted_at IS NULL AND valid_to IS NULL
                ORDER BY updated_at ASC
                """
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def save_memory_embedding(
        self,
        memory_id: str,
        content_hash: str,
        model_id: str,
        vector: list[float],
    ) -> None:
        if len(vector) != 512:
            raise ValueError("embedding_dimension_mismatch")
        payload = array("f", vector).tobytes()
        now = iso_now()
        with self.database.connect() as connection:
            self._remove_memory_embedding(connection, memory_id)
            connection.execute(
                """
                INSERT INTO memory_embeddings(
                    memory_id, content_hash, model_id, dimensions, indexed_at
                ) VALUES(?, ?, ?, 512, ?)
                """,
                (memory_id, content_hash, model_id, now),
            )
            try:
                connection.execute(
                    "INSERT INTO memory_vectors(memory_id, embedding) VALUES(?, ?)",
                    (memory_id, payload),
                )
            except sqlite3.OperationalError as error:
                connection.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id=?",
                    (memory_id,),
                )
                raise RuntimeError("sqlite_vec_unavailable") from error

    def memory_vector_search(
        self,
        vector: list[float],
        query: MemoryQuery,
        limit: int,
    ) -> list[MemoryRecord]:
        if len(vector) != 512:
            return []
        payload = array("f", vector).tobytes()
        try:
            with self.database.connect() as connection:
                nearest = connection.execute(
                    """
                    SELECT memory_id
                    FROM memory_vectors
                    WHERE embedding MATCH ? AND k = ?
                    ORDER BY distance
                    """,
                    (payload, max(limit * 4, 20)),
                ).fetchall()
        except (sqlite3.Error, RuntimeError):
            return []
        ranked_ids = [row["memory_id"] for row in nearest]
        if not ranked_ids:
            return []
        records = {item.id: item for item in self.memories_by_ids(ranked_ids, query)}
        return [records[memory_id] for memory_id in ranked_ids if memory_id in records][
            :limit
        ]

    def memories_by_ids(
        self,
        memory_ids: list[str],
        query: MemoryQuery,
    ) -> list[MemoryRecord]:
        if not memory_ids:
            return []
        placeholders = ",".join("?" for _ in memory_ids)
        conditions = [
            f"id IN ({placeholders})",
            "deleted_at IS NULL",
            "valid_to IS NULL",
        ]
        params: list[Any] = list(memory_ids)
        if query.kinds:
            kind_placeholders = ",".join("?" for _ in query.kinds)
            conditions.append(f"kind IN ({kind_placeholders})")
            params.extend(query.kinds)
        if query.starred_only:
            conditions.append("starred=1")
        if not query.include_sensitive:
            conditions.append("sensitivity='normal'")
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM memories WHERE {' AND '.join(conditions)}",
                params,
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def memory_index_status(self, model_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            active_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM memories
                    WHERE deleted_at IS NULL AND valid_to IS NULL
                    """
                ).fetchone()[0]
            )
            indexed_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM memory_embeddings WHERE model_id=?",
                    (model_id,),
                ).fetchone()[0]
            )
            state = connection.execute(
                "SELECT * FROM memory_index_state WHERE id=1"
            ).fetchone()
        return {
            "status": state["status"] if state else "disabled",
            "model": state["model_id"] if state else model_id,
            "dimensions": state["dimensions"] if state else None,
            "indexed_count": indexed_count,
            "pending_count": max(0, active_count - indexed_count),
            "last_error": state["last_error"] if state else None,
        }

    def set_memory_index_state(
        self,
        status: str,
        model_id: str,
        *,
        dimensions: int | None = None,
        last_error: str | None = None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_index_state(
                    id, status, model_id, dimensions, last_error, updated_at
                ) VALUES(1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    model_id=excluded.model_id,
                    dimensions=excluded.dimensions,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (status, model_id, dimensions, last_error, iso_now()),
            )

    def clear_memory_embeddings(self) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM memory_embeddings")
            try:
                connection.execute("DELETE FROM memory_vectors")
            except sqlite3.OperationalError:
                pass

    def count_messages(self, session_id: str) -> int:
        with self.database.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id=?",
                    (session_id,),
                ).fetchone()[0]
            )

    def summary_messages(
        self,
        session_id: str,
        *,
        keep_recent: int = 12,
    ) -> list[MessageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE session_id=?
                ORDER BY created_at ASC, rowid ASC
                LIMIT MAX(
                    (SELECT COUNT(*) FROM messages WHERE session_id=?) - ?,
                    0
                )
                """,
                (session_id, session_id, keep_recent),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def create_summary_job(
        self,
        session_id: str,
        messages: list[MessageRecord],
        provider: str | None,
        model: str | None,
    ) -> ConversationSummaryRecord:
        if not messages:
            raise ValueError("summary_has_no_messages")
        now = utc_now()
        record = ConversationSummaryRecord(
            id=str(uuid4()),
            session_id=session_id,
            first_message_id=messages[0].id,
            last_message_id=messages[-1].id,
            message_count=len(messages),
            content="",
            status="pending",
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_summaries(
                    id, session_id, first_message_id, last_message_id,
                    message_count, content, status, provider, model,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, '', 'pending', ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.session_id,
                    record.first_message_id,
                    record.last_message_id,
                    record.message_count,
                    record.provider,
                    record.model,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record

    def complete_summary(self, summary_id: str, content: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE conversation_summaries
                SET content=?, status='ready', error_code=NULL, updated_at=?
                WHERE id=? AND deleted_at IS NULL
                """,
                (content, iso_now(), summary_id),
            )

    def fail_summary(self, summary_id: str, status: str, error_code: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE conversation_summaries
                SET status=?, error_code=?, updated_at=?
                WHERE id=? AND deleted_at IS NULL
                """,
                (status, error_code, iso_now(), summary_id),
            )

    def list_summaries(
        self,
        *,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ConversationSummaryRecord], int]:
        conditions = ["deleted_at IS NULL"]
        params: list[Any] = []
        if session_id:
            conditions.append("session_id=?")
            params.append(session_id)
        condition = f"WHERE {' AND '.join(conditions)}"
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM conversation_summaries {condition}",
                    params,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT * FROM conversation_summaries {condition}
                ORDER BY updated_at DESC LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return [self._summary_from_row(row) for row in rows], total

    def active_summary(self, session_id: str) -> ConversationSummaryRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM conversation_summaries
                WHERE session_id=? AND status='ready' AND deleted_at IS NULL
                ORDER BY updated_at DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return self._summary_from_row(row) if row else None

    def latest_summary_coverage(self, session_id: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(message_count), 0)
                FROM conversation_summaries WHERE session_id=?
                """,
                (session_id,),
            ).fetchone()
        return int(row[0])

    def delete_summary(self, summary_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE conversation_summaries
                SET status='deleted', deleted_at=?, updated_at=?
                WHERE id=? AND deleted_at IS NULL
                """,
                (iso_now(), iso_now(), summary_id),
            )
        return cursor.rowcount > 0

    def pending_summary_ids(self) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id FROM conversation_summaries
                WHERE status='pending' AND deleted_at IS NULL
                """
            ).fetchall()
        return [row["id"] for row in rows]

    def summary_job(self, summary_id: str) -> ConversationSummaryRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_summaries WHERE id=?",
                (summary_id,),
            ).fetchone()
        return self._summary_from_row(row) if row else None

    def create_plan(self, value: PlanCreate) -> PlanRecord:
        now = utc_now()
        record = PlanRecord(
            id=str(uuid4()),
            status="pending",
            progress=0,
            created_at=now,
            updated_at=now,
            **value.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(
                    id, title, description, category, due_at, reminder_at,
                    source, status, progress, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.title,
                    record.description,
                    record.category,
                    record.due_at.isoformat() if record.due_at else None,
                    record.reminder_at.isoformat() if record.reminder_at else None,
                    record.source,
                    record.status,
                    record.progress,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record

    def list_plans(self, include_completed: bool = True) -> list[PlanRecord]:
        sql = "SELECT * FROM tasks"
        params: tuple[Any, ...] = ()
        if not include_completed:
            sql += " WHERE status NOT IN ('completed', 'cancelled')"
        sql += " ORDER BY COALESCE(due_at, '9999') ASC, created_at ASC"
        with self.database.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._plan_from_row(row) for row in rows]

    def update_plan(self, plan_id: str, value: PlanUpdate) -> PlanRecord | None:
        changes = value.model_dump(exclude_none=True)
        if not changes:
            return self.get_plan(plan_id)
        assignments: list[str] = []
        params: list[Any] = []
        for key, item in changes.items():
            assignments.append(f"{key}=?")
            if isinstance(item, datetime):
                params.append(item.isoformat())
            else:
                params.append(item)
        if changes.get("status") == "completed":
            assignments.append("progress=?")
            params.append(1.0)
        assignments.append("updated_at=?")
        params.append(iso_now())
        params.append(plan_id)
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"UPDATE tasks SET {', '.join(assignments)} WHERE id=?",
                params,
            )
        return self.get_plan(plan_id) if cursor.rowcount else None

    def get_plan(self, plan_id: str) -> PlanRecord | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (plan_id,)).fetchone()
        return self._plan_from_row(row) if row else None

    def delete_plan(self, plan_id: str) -> bool:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM proactive_events WHERE reason=?",
                (plan_id,),
            )
            cursor = connection.execute("DELETE FROM tasks WHERE id=?", (plan_id,))
        return cursor.rowcount > 0

    def claim_due_plan_reminders(
        self, current: datetime
    ) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        current_iso = current.isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT tasks.*
                FROM tasks
                WHERE reminder_at IS NOT NULL
                  AND reminder_at <= ?
                  AND status NOT IN ('completed', 'cancelled')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM proactive_events
                    WHERE event_type='plan.reminder_due'
                      AND reason=tasks.id
                  )
                ORDER BY reminder_at ASC
                """,
                (current_iso,),
            ).fetchall()
            for row in rows:
                task = self._plan_from_row(row)
                event_id = str(uuid4())
                payload = {"task": task.model_dump(mode="json")}
                connection.execute(
                    """
                    INSERT INTO proactive_events(
                        id, event_type, reason, payload_json, status,
                        scheduled_at, created_at
                    ) VALUES(?, 'plan.reminder_due', ?, ?, 'dispatching', ?, ?)
                    """,
                    (
                        event_id,
                        task.id,
                        json.dumps(payload, ensure_ascii=False),
                        task.reminder_at.isoformat() if task.reminder_at else None,
                        current_iso,
                    ),
                )
                claimed.append({"event_id": event_id, **payload})
        return claimed

    def mark_proactive_event_delivered(self, event_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE proactive_events
                SET status='delivered', delivered_at=?
                WHERE id=?
                """,
                (iso_now(), event_id),
            )

    def claim_proactive_checkin(
        self,
        current: datetime,
        *,
        daily_limit: int,
        cooldown_minutes: int,
        inactivity_minutes: int,
    ) -> dict[str, Any] | None:
        if daily_limit <= 0:
            return None
        current_utc = current.astimezone(timezone.utc)
        local_current = current.astimezone()
        local_start = local_current.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        day_start = local_start.astimezone(timezone.utc)
        day_end = (local_start + timedelta(days=1)).astimezone(timezone.utc)
        with self.database.connect() as connection:
            last_message = connection.execute(
                """
                SELECT created_at
                FROM messages
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()
            if not last_message:
                return None
            last_interaction = datetime.fromisoformat(last_message["created_at"])
            if last_interaction.tzinfo is None:
                last_interaction = last_interaction.replace(tzinfo=timezone.utc)
            inactive_for = current_utc - last_interaction.astimezone(timezone.utc)
            if inactive_for < timedelta(minutes=max(0, inactivity_minutes)):
                return None

            delivered_today = connection.execute(
                """
                SELECT COUNT(*)
                FROM proactive_events
                WHERE event_type='companion.checkin_due'
                  AND created_at >= ?
                  AND created_at < ?
                  AND status IN ('dispatching', 'delivered', 'acknowledged')
                """,
                (day_start.isoformat(), day_end.isoformat()),
            ).fetchone()[0]
            if delivered_today >= daily_limit:
                return None

            latest_checkin = connection.execute(
                """
                SELECT created_at
                FROM proactive_events
                WHERE event_type='companion.checkin_due'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
            if latest_checkin:
                latest_at = datetime.fromisoformat(latest_checkin["created_at"])
                if latest_at.tzinfo is None:
                    latest_at = latest_at.replace(tzinfo=timezone.utc)
                if current_utc - latest_at.astimezone(timezone.utc) < timedelta(
                    minutes=max(0, cooldown_minutes)
                ):
                    return None

            local_hour = local_current.hour
            if local_hour < 12:
                message = "早呀，今天也按自己的节奏慢慢来。"
            elif local_hour < 18:
                message = "忙了一阵的话，记得给自己留一点喘息时间。"
            else:
                message = "晚上好，忙完了就回来坐一会儿吧。"
            inactive_minutes = max(0, int(inactive_for.total_seconds() // 60))
            payload = {
                "kind": "gentle_checkin",
                "message": message,
                "reason": f"距离上次交流约 {inactive_minutes} 分钟",
            }
            event_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO proactive_events(
                    id, event_type, reason, payload_json, status,
                    scheduled_at, created_at
                ) VALUES(
                    ?, 'companion.checkin_due', 'inactivity_checkin', ?,
                    'dispatching', ?, ?
                )
                """,
                (
                    event_id,
                    json.dumps(payload, ensure_ascii=False),
                    current_utc.isoformat(),
                    current_utc.isoformat(),
                ),
            )
        return {"event_id": event_id, **payload}

    def list_notifications(
        self, *, include_acknowledged: bool = False, limit: int = 50
    ) -> list[NotificationRecord]:
        status_clause = (
            "status IN ('delivered', 'acknowledged')"
            if include_acknowledged
            else "status='delivered'"
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM proactive_events
                WHERE {status_clause}
                ORDER BY COALESCE(delivered_at, created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            NotificationRecord(
                id=row["id"],
                event_type=row["event_type"],
                reason=row["reason"],
                payload=_json(row["payload_json"], {}),
                status=row["status"],
                scheduled_at=row["scheduled_at"],
                delivered_at=row["delivered_at"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def acknowledge_notification(self, notification_id: str) -> NotificationRecord | None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE proactive_events
                SET status='acknowledged'
                WHERE id=? AND status IN ('delivered', 'acknowledged')
                """,
                (notification_id,),
            )
            row = connection.execute(
                "SELECT * FROM proactive_events WHERE id=?",
                (notification_id,),
            ).fetchone()
        if not cursor.rowcount or not row:
            return None
        return NotificationRecord(
            id=row["id"],
            event_type=row["event_type"],
            reason=row["reason"],
            payload=_json(row["payload_json"], {}),
            status=row["status"],
            scheduled_at=row["scheduled_at"],
            delivered_at=row["delivered_at"],
            created_at=row["created_at"],
        )

    def active_persona(self) -> PersonaRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM personas WHERE active=1 ORDER BY version DESC LIMIT 1"
            ).fetchone()
        if not row:
            raise RuntimeError("No active persona")
        return self._persona_from_row(row)

    def create_persona_version(self, value: PersonaUpdate) -> PersonaRecord:
        with self.database.connect() as connection:
            version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM personas"
            ).fetchone()[0]
            connection.execute("UPDATE personas SET active=0 WHERE active=1")
            persona_id = str(uuid4())
            created_at = iso_now()
            connection.execute(
                """
                INSERT INTO personas(
                    id, version, name, relationship_role, background,
                    voice_json, behavior_json, boundaries_json, active, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    persona_id,
                    version,
                    value.name,
                    value.relationship_role,
                    value.background,
                    json.dumps(value.voice, ensure_ascii=False),
                    json.dumps(value.behavior, ensure_ascii=False),
                    json.dumps(value.boundaries, ensure_ascii=False),
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM personas WHERE id=?", (persona_id,)
            ).fetchone()
        return self._persona_from_row(row)

    def current_mood(self) -> MoodRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM mood_states ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return self._mood_from_row(row)

    def set_mood(self, value: MoodUpdate) -> MoodRecord:
        record = MoodRecord(id=str(uuid4()), created_at=utc_now(), **value.model_dump())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO mood_states(
                    id, valence, arousal, energy, closeness, stress, reason, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.valence,
                    record.arousal,
                    record.energy,
                    record.closeness,
                    record.stress,
                    record.reason,
                    record.created_at.isoformat(),
                ),
            )
        return record

    def list_models(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM model_registry ORDER BY required DESC, kind"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "provider": row["provider"],
                "status": row["status"],
                "required": bool(row["required"]),
                "metadata": _json(row["metadata_json"], {}),
            }
            for row in rows
        ]

    def set_model_status(
        self, model_id: str, provider: str, status: str, metadata: dict[str, Any]
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE model_registry
                SET provider=?, status=?, metadata_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    provider,
                    status,
                    json.dumps(metadata, ensure_ascii=False),
                    iso_now(),
                    model_id,
                ),
            )

    def get_settings(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT key, value_json FROM settings").fetchall()
        return {row["key"]: _json(row["value_json"], None) for row in rows}

    def diagnostic_counts(self) -> dict[str, int]:
        queries = {
            "conversations": "SELECT COUNT(*) FROM sessions",
            "messages": "SELECT COUNT(*) FROM messages",
            "memories": (
                "SELECT COUNT(*) FROM memories WHERE deleted_at IS NULL"
            ),
            "plans": (
                "SELECT COUNT(*) FROM tasks "
                "WHERE status NOT IN ('completed', 'cancelled')"
            ),
            "notifications_unread": (
                "SELECT COUNT(*) FROM proactive_events WHERE status='delivered'"
            ),
            "persona_versions": "SELECT COUNT(*) FROM personas",
        }
        with self.database.connect() as connection:
            return {
                key: int(connection.execute(sql).fetchone()[0])
                for key, sql in queries.items()
            }

    def set_setting(self, key: str, value: Any) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value_json, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE
                SET value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False), iso_now()),
            )

    def export_data(self) -> DataExport:
        output: dict[str, list[dict[str, Any]]] = {}
        with self.database.connect() as connection:
            for table in self.export_tables:
                rows = connection.execute(f"SELECT * FROM {table}").fetchall()
                output[table] = [dict(row) for row in rows]
            version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
        return DataExport(schema_version=version, exported_at=utc_now(), data=output)

    def import_data(
        self,
        schema_version: int,
        data: dict[str, list[dict[str, Any]]],
    ) -> int:
        if schema_version not in {1, self.database.current_schema_version}:
            raise ValueError("Import schema version is not supported")
        target_tables = tuple(
            table for table in self.export_tables if table != "model_registry"
        )
        source_tables = (
            tuple(table for table in target_tables if table != "conversation_summaries")
            if schema_version == 1
            else target_tables
        )
        missing = set(source_tables).difference(data)
        unknown = set(data).difference(self.export_tables)
        if missing:
            raise ValueError(
                f"Import is missing required tables: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise ValueError(
                f"Import contains unknown tables: {', '.join(sorted(unknown))}"
            )
        personas = data["personas"]
        if not personas or sum(bool(item.get("active")) for item in personas) != 1:
            raise ValueError("Import must contain exactly one active persona")

        imported_rows = 0
        with self.database.connect() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            for table in reversed(target_tables):
                connection.execute(f"DELETE FROM {table}")
            connection.execute("DELETE FROM memory_search")
            connection.execute("DELETE FROM memory_embeddings")
            try:
                connection.execute("DELETE FROM memory_vectors")
            except sqlite3.OperationalError:
                pass

            for table in source_tables:
                columns = {
                    row["name"]
                    for row in connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                }
                for row in data[table]:
                    if not row or not set(row).issubset(columns):
                        raise ValueError(f"Import row does not match table {table}")
                    names = list(row)
                    placeholders = ", ".join("?" for _ in names)
                    values = [
                        (
                            json.dumps(value, ensure_ascii=False)
                            if isinstance(value, (dict, list))
                            else value
                        )
                        for value in row.values()
                    ]
                    connection.execute(
                        f"""
                        INSERT INTO {table}({', '.join(names)})
                        VALUES({placeholders})
                        """,
                        values,
                    )
                    imported_rows += 1

            for memory in data["memories"]:
                if memory.get("deleted_at") is None:
                    self._index_memory(
                        connection,
                        memory["id"],
                        memory["kind"],
                        memory["title"],
                        memory["content"],
                    )
            connection.execute("PRAGMA foreign_keys = ON")
        self.database.initialize()
        return imported_rows

    def delete_user_data(self) -> None:
        protected = {"schema_migrations", "model_registry"}
        with self.database.connect() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            for table in reversed(self.export_tables):
                if table not in protected:
                    connection.execute(f"DELETE FROM {table}")
            connection.execute("DELETE FROM memory_search")
            connection.execute("DELETE FROM memory_embeddings")
            try:
                connection.execute("DELETE FROM memory_vectors")
            except sqlite3.OperationalError:
                pass
            connection.execute("PRAGMA foreign_keys = ON")
        self.database.initialize()

    @staticmethod
    def _index_memory(
        connection: sqlite3.Connection,
        memory_id: str,
        kind: str,
        title: str,
        content: str,
    ) -> None:
        connection.execute("DELETE FROM memory_search WHERE memory_id=?", (memory_id,))
        connection.execute(
            "INSERT INTO memory_search(memory_id, kind, title, content) VALUES(?, ?, ?, ?)",
            (memory_id, kind, title, content),
        )

    @staticmethod
    def _remove_memory_embedding(
        connection: sqlite3.Connection,
        memory_id: str,
    ) -> None:
        connection.execute(
            "DELETE FROM memory_embeddings WHERE memory_id=?",
            (memory_id,),
        )
        try:
            connection.execute(
                "DELETE FROM memory_vectors WHERE memory_id=?",
                (memory_id,),
            )
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            metadata=_json(row["metadata_json"], {}),
        )

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> ConversationSummaryRecord:
        return ConversationSummaryRecord(
            id=row["id"],
            session_id=row["session_id"],
            first_message_id=row["first_message_id"],
            last_message_id=row["last_message_id"],
            message_count=row["message_count"],
            content=row["content"],
            status=row["status"],
            provider=row["provider"],
            model=row["model"],
            error_code=row["error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    @staticmethod
    def _memory_from_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            content=row["content"],
            source=row["source"],
            source_message_id=row["source_message_id"],
            confidence=row["confidence"],
            salience=row["salience"],
            user_confirmed=bool(row["user_confirmed"]),
            sensitivity=row["sensitivity"],
            starred=bool(row["starred"]),
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            supersedes_id=row["supersedes_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _plan_from_row(row: sqlite3.Row) -> PlanRecord:
        return PlanRecord(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            category=row["category"],
            due_at=row["due_at"],
            reminder_at=row["reminder_at"],
            source=row["source"],
            status=row["status"],
            progress=row["progress"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _persona_from_row(row: sqlite3.Row) -> PersonaRecord:
        return PersonaRecord(
            id=row["id"],
            version=row["version"],
            name=row["name"],
            relationship_role=row["relationship_role"],
            background=row["background"],
            voice=_json(row["voice_json"], {}),
            behavior=_json(row["behavior_json"], {}),
            boundaries=_json(row["boundaries_json"], {}),
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _mood_from_row(row: sqlite3.Row) -> MoodRecord:
        return MoodRecord(
            id=row["id"],
            valence=row["valence"],
            arousal=row["arousal"],
            energy=row["energy"],
            closeness=row["closeness"],
            stress=row["stress"],
            reason=row["reason"],
            created_at=row["created_at"],
        )
