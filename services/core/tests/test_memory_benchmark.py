from pathlib import Path

import pytest

from xinyu_core.memory_benchmark import run_memory_benchmark


def test_memory_benchmark_is_repeatable_and_private(tmp_path: Path) -> None:
    first = run_memory_benchmark(
        tmp_path / "first.db", count=250, seed=17, query_count=20
    )
    second = run_memory_benchmark(
        tmp_path / "second.db", count=250, seed=17, query_count=20
    )

    assert first.count == second.count == 250
    assert first.seed == second.seed == 17
    assert first.queries == second.queries == 20
    assert first.top5_hit_rate == second.top5_hit_rate == 1.0
    assert first.mode == "fts5_synthetic"
    assert first.database_size_bytes > 0
    assert first.query_p95_ms >= first.query_p50_ms >= 0


def test_memory_benchmark_never_overwrites_an_existing_database(
    tmp_path: Path,
) -> None:
    target = tmp_path / "existing.db"
    target.write_bytes(b"keep-me")

    with pytest.raises(
        FileExistsError, match="benchmark_database_already_exists"
    ):
        run_memory_benchmark(target, count=10)

    assert target.read_bytes() == b"keep-me"
