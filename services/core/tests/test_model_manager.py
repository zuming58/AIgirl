import asyncio
from pathlib import Path

from xinyu_core.avatar import AvatarRuntime
from xinyu_core.config import AppConfig
from xinyu_core.contracts import GpuCapability, SystemCapabilities
from xinyu_core.model_manager import ModelManager
from xinyu_core.model_manager import ModelProcessNotRegistered
from xinyu_core.model_manager import ModelProcessSupervisor
from xinyu_core.speech import SpeechRuntime


def capabilities(gpu_memory_mb: int = 16_384, memory_gb: float = 32) -> SystemCapabilities:
    return SystemCapabilities(
        platform="Windows 11",
        cpu="test-cpu",
        logical_cores=24,
        memory_gb=memory_gb,
        gpus=[
            GpuCapability(
                name="RTX 4070 Ti SUPER",
                memory_mb=gpu_memory_mb,
            )
        ],
        recommended_profile="high_quality_16gb",
        avatar_strategy="test",
        notes=[],
    )


def config(tmp_path: Path, **changes: object) -> AppConfig:
    values: dict[str, object] = {
        "data_dir": tmp_path,
        "database_path": tmp_path / "xinyu.db",
    }
    values.update(changes)
    return AppConfig(**values)  # type: ignore[arg-type]


def test_safe_fallback_is_explicit_and_never_claims_voice_models_ready(tmp_path: Path) -> None:
    manager = ModelManager(
        config(tmp_path),
        capabilities(),
        SpeechRuntime(None),
        AvatarRuntime(tmp_path),
    )

    plan = manager.plan()

    assert plan.profile == "safe_fallback"
    assert plan.status == "degraded"
    assert plan.validation_errors == ["safe_fallback_active"]
    components = {component.id: component for component in plan.components}
    assert components["stt-local"].status == "unavailable"
    assert not components["stt-local"].required


def test_quality_local_checks_configuration_and_gpu_budget(tmp_path: Path) -> None:
    manager = ModelManager(
        config(
            tmp_path,
            runtime_profile="quality_local",
            tts_model="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        ),
        capabilities(gpu_memory_mb=8_000, memory_gb=16),
        SpeechRuntime(None),
        AvatarRuntime(tmp_path),
    )

    plan = manager.plan()

    assert plan.status == "degraded"
    assert set(plan.validation_errors) == {
        "insufficient_gpu_memory",
        "insufficient_system_memory",
        "llm_not_configured",
        "voice_not_configured",
        "tts_model_exceeds_quality_local_budget",
    }
    assert plan.budget.tts_max_mb == 4_000
    assert next(item for item in plan.components if item.id == "llm-local").required


def test_quality_cloud_llm_requires_an_endpoint_but_allows_the_experiment_tts_tier(
    tmp_path: Path,
) -> None:
    manager = ModelManager(
        config(
            tmp_path,
            runtime_profile="quality_cloud_llm",
            speech_realtime_url="ws://127.0.0.1:8766/v1/realtime",
            tts_model="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        ),
        capabilities(),
        SpeechRuntime("ws://127.0.0.1:8766/v1/realtime"),
        AvatarRuntime(tmp_path),
    )

    plan = manager.plan()

    assert "llm_not_configured" in plan.validation_errors
    assert "tts_model_exceeds_quality_local_budget" not in plan.validation_errors
    assert plan.budget.tts_max_mb == 5_000


def test_llm_health_check_does_not_treat_a_configured_but_failed_endpoint_as_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class Response:
        status_code = 503

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("xinyu_core.model_manager.httpx.Client", lambda **kwargs: Client())
    manager = ModelManager(
        config(tmp_path, runtime_profile="quality_cloud_llm", llm_base_url="http://127.0.0.1:8080/v1"),
        capabilities(),
        SpeechRuntime(None),
        AvatarRuntime(tmp_path),
    )

    plan = manager.plan()

    assert "llm_http_503" in plan.validation_errors
    llm = next(item for item in plan.components if item.id == "llm-local")
    assert llm.status == "degraded"


def test_model_process_lifecycle_isolated_failure_and_restart() -> None:
    class FakeProcess:
        pid = 4321

        def __init__(self) -> None:
            self.returncode = None
            self.exited = asyncio.Event()

        def terminate(self) -> None:
            self.returncode = 0
            self.exited.set()

        def kill(self) -> None:
            self.returncode = -9
            self.exited.set()

        async def wait(self) -> int:
            await self.exited.wait()
            return self.returncode or 0

    processes: list[FakeProcess] = []

    async def factory(command):
        process = FakeProcess()
        processes.append(process)
        return process

    events = []

    async def sink(event):
        events.append((event.model_id, event.state, event.detail))

    async def exercise():
        supervisor = ModelProcessSupervisor(event_sink=sink)
        supervisor.register("stt-local", ["fake-stt"], factory=factory)
        started = await supervisor.start("stt-local")
        assert started.state == "running"
        processes[0].returncode = 17
        processes[0].exited.set()
        await asyncio.sleep(0.01)
        failed = supervisor.statuses()[0]
        assert failed.state == "failed"
        assert failed.last_error == "process_exit:17"
        restarted = await supervisor.restart("stt-local")
        assert restarted.state == "running"
        assert restarted.restart_count == 1
        stopped = await supervisor.stop("stt-local")
        assert stopped.state == "stopped"
        assert any(state == "failed" for _, state, _ in events)

    asyncio.run(exercise())


def test_model_process_concurrent_start_only_spawns_once() -> None:
    class FakeProcess:
        pid = 101

        async def wait(self) -> int:
            await asyncio.Future()

        def terminate(self) -> None:
            raise AssertionError("not stopped in this test")

    calls = 0
    release = asyncio.Event()

    async def factory(command):
        nonlocal calls
        calls += 1
        await release.wait()
        return FakeProcess()

    async def exercise():
        supervisor = ModelProcessSupervisor()
        supervisor.register("llm-local", ["local-test"], factory=factory)
        first, second = asyncio.create_task(supervisor.start("llm-local")), asyncio.create_task(
            supervisor.start("llm-local")
        )
        for _ in range(3):
            await asyncio.sleep(0)
        assert calls == 1
        release.set()
        statuses = await asyncio.gather(first, second)
        assert calls == 1
        assert all(status.state == "running" for status in statuses)
        first.cancel()
        second.cancel()

    asyncio.run(exercise())


def test_model_process_stop_timeout_uses_kill_fallback() -> None:
    class FakeProcess:
        pid = 202

        def __init__(self) -> None:
            self.killed = False

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            if self.killed:
                return -9
            await asyncio.Future()

    process = FakeProcess()

    async def factory(command):
        return process

    async def exercise():
        supervisor = ModelProcessSupervisor()
        supervisor.register(
            "speech-runtime",
            ["local-test"],
            factory=factory,
            stop_timeout=0.01,
        )
        await supervisor.start("speech-runtime")
        stopped = await supervisor.stop("speech-runtime")
        assert process.killed is True
        assert stopped.state == "stopped"
        assert stopped.pid is None

    asyncio.run(exercise())


def test_model_process_start_timeout_has_stable_error_code() -> None:
    async def factory(command):
        await asyncio.Future()

    async def exercise():
        supervisor = ModelProcessSupervisor()
        supervisor.register(
            "llm-local",
            ["local-test"],
            factory=factory,
            start_timeout=0.01,
        )
        status = await supervisor.start("llm-local")
        assert status.state == "failed"
        assert status.last_error == "process_start_timeout"
        assert status.pid is None

    asyncio.run(exercise())


def test_model_process_unknown_id_has_stable_error() -> None:
    async def exercise():
        supervisor = ModelProcessSupervisor()
        try:
            await supervisor.start("not-registered")
        except ModelProcessNotRegistered as error:
            assert error.args == ("not-registered",)
        else:
            raise AssertionError("expected a stable unknown-process error")

    asyncio.run(exercise())


def test_process_command_env_accepts_only_json_argument_arrays(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XINYU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "XINYU_LLM_PROCESS_COMMAND_JSON",
        '["llama-server.exe", "--model", "companion.gguf"]',
    )
    monkeypatch.setenv("XINYU_SPEECH_PROCESS_COMMAND_JSON", "llama-server.exe --model unsafe")
    configured = AppConfig.from_env()

    assert configured.llm_process_command == (
        "llama-server.exe",
        "--model",
        "companion.gguf",
    )
    assert configured.speech_process_command == ()
