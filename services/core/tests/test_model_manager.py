from pathlib import Path

from xinyu_core.avatar import AvatarRuntime
from xinyu_core.config import AppConfig
from xinyu_core.contracts import GpuCapability, SystemCapabilities
from xinyu_core.model_manager import ModelManager
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
