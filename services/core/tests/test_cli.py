import sys

import pytest

from xinyu_core import cli


def test_cli_starts_loopback_server_with_parent_watch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "xinyu-core",
            "--host",
            "localhost",
            "--port",
            "9876",
            "--parent-pid",
            "123",
        ],
    )
    monkeypatch.setattr(
        cli,
        "watch_parent_process",
        lambda parent_pid: calls.update(parent_pid=parent_pid),
    )
    monkeypatch.setattr(
        cli.uvicorn,
        "run",
        lambda *args, **kwargs: calls.update(args=args, kwargs=kwargs),
    )

    cli.main()

    assert calls["parent_pid"] == 123
    assert calls["kwargs"]["host"] == "localhost"
    assert calls["kwargs"]["port"] == 9876
    assert calls["kwargs"]["factory"] is True


def test_cli_rejects_non_loopback_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["xinyu-core", "--host", "0.0.0.0"],
    )
    with pytest.raises(SystemExit):
        cli.main()


def test_parent_watch_is_a_noop_without_a_parent() -> None:
    cli.watch_parent_process(None)
