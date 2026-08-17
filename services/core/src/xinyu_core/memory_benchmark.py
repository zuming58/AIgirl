from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .contracts import MemoryQuery
from .database import Database
from .repository import Repository


@dataclass(frozen=True, slots=True)
class MemoryBenchmarkResult:
    count: int
    seed: int
    database_size_bytes: int
    insert_seconds: float
    queries: int
    query_p50_ms: float
    query_p95_ms: float
    top5_hit_rate: float
    mode: str = "fts5_synthetic"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _row(index: int, seed: int, timestamp: str) -> tuple[object, ...]:
    marker = f"xinyubench_{seed}_{index:06d}"
    kind = ("preference", "profile", "episode", "commitment")[index % 4]
    title = f"合成记忆 {index:06d}"
    content = f"{marker} 固定种子合成内容，批次 {index // 1000:03d}。"
    return (
        f"benchmark-{seed}-{index:06d}",
        kind,
        title,
        content,
        "tool_result",
        0.8,
        round(0.2 + (index % 7) * 0.1, 2),
        1,
        "normal",
        int(index % 97 == 0),
        timestamp,
        timestamp,
        timestamp,
    )


def seed_synthetic_memories(
    database: Database,
    *,
    count: int,
    seed: int,
    batch_size: int = 2000,
) -> float:
    if count < 1:
        raise ValueError("count_must_be_positive")
    if batch_size < 1:
        raise ValueError("batch_size_must_be_positive")
    database.initialize()
    started = time.perf_counter()
    timestamp = datetime.now(timezone.utc).isoformat()
    with database.connect() as connection:
        existing = connection.execute(
            "SELECT COUNT(*) FROM memories"
        ).fetchone()[0]
        if existing:
            raise ValueError("benchmark_database_not_empty")
        for start in range(0, count, batch_size):
            rows = [
                _row(index, seed, timestamp)
                for index in range(start, min(count, start + batch_size))
            ]
            connection.executemany(
                """
                INSERT INTO memories(
                    id, kind, title, content, source, confidence, salience,
                    user_confirmed, sensitivity, starred, valid_from,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.executemany(
                """
                INSERT INTO memory_search(memory_id, kind, title, content)
                VALUES(?, ?, ?, ?)
                """,
                [(row[0], row[1], row[2], row[3]) for row in rows],
            )
    return time.perf_counter() - started


def run_memory_benchmark(
    database_path: Path,
    *,
    count: int = 100_000,
    seed: int = 20260804,
    query_count: int = 100,
) -> MemoryBenchmarkResult:
    if database_path.exists():
        raise FileExistsError("benchmark_database_already_exists")
    database = Database(database_path)
    insert_seconds = seed_synthetic_memories(
        database, count=count, seed=seed
    )
    repository = Repository(database)
    latencies: list[float] = []
    hits = 0
    queries = min(max(1, query_count), count)
    for position in range(queries):
        index = (position * 7919 + seed) % count
        marker = f"xinyubench_{seed}_{index:06d}"
        started = time.perf_counter()
        results = repository.query_memories(
            MemoryQuery(query=marker, limit=5)
        )
        latencies.append((time.perf_counter() - started) * 1000)
        expected_id = f"benchmark-{seed}-{index:06d}"
        hits += int(any(item.id == expected_id for item in results))
    return MemoryBenchmarkResult(
        count=count,
        seed=seed,
        database_size_bytes=database_path.stat().st_size,
        insert_seconds=round(insert_seconds, 3),
        queries=queries,
        query_p50_ms=round(_percentile(latencies, 0.50), 3),
        query_p95_ms=round(_percentile(latencies, 0.95), 3),
        top5_hit_rate=round(hits / queries, 4),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and query an isolated synthetic Xinyu memory database."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()
    result = run_memory_benchmark(
        args.database.resolve(),
        count=args.count,
        seed=args.seed,
        query_count=args.queries,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
