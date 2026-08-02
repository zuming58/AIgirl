from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .avatar import AvatarRuntime
from .config import AppConfig
from .contracts import (
    ModelRuntimeBudget,
    ModelRuntimePlan,
    RuntimeComponent,
    SystemCapabilities,
)
from .speech import SpeechRuntime, SpeechRuntimeStatus


RuntimeProfile = Literal["quality_local", "quality_cloud_llm", "safe_fallback"]
ComponentStatus = Literal["ready", "degraded", "unavailable", "disabled"]


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    name: RuntimeProfile
    gpu_memory_mb: int
    system_memory_gb: int
    budget: ModelRuntimeBudget
    needs_llm_endpoint: bool
    needs_voice: bool


PROFILE_SPECS: dict[RuntimeProfile, ProfileSpec] = {
    "quality_local": ProfileSpec(
        name="quality_local",
        gpu_memory_mb=14_000,
        system_memory_gb=28,
        budget=ModelRuntimeBudget(
            gpu_budget_mb=16_000,
            llm_max_mb=7_000,
            stt_max_mb=1_500,
            tts_max_mb=4_000,
            avatar_max_mb=0,
        ),
        needs_llm_endpoint=True,
        needs_voice=True,
    ),
    "quality_cloud_llm": ProfileSpec(
        name="quality_cloud_llm",
        gpu_memory_mb=14_000,
        system_memory_gb=28,
        budget=ModelRuntimeBudget(
            gpu_budget_mb=16_000,
            llm_max_mb=0,
            stt_max_mb=1_500,
            tts_max_mb=5_000,
            avatar_max_mb=0,
        ),
        needs_llm_endpoint=True,
        needs_voice=True,
    ),
    "safe_fallback": ProfileSpec(
        name="safe_fallback",
        gpu_memory_mb=0,
        system_memory_gb=0,
        budget=ModelRuntimeBudget(
            gpu_budget_mb=0,
            llm_max_mb=0,
            stt_max_mb=0,
            tts_max_mb=0,
            avatar_max_mb=0,
        ),
        needs_llm_endpoint=False,
        needs_voice=False,
    ),
}


class ModelManager:
    """Describe model readiness without owning model processes or weights."""

    def __init__(
        self,
        config: AppConfig,
        capabilities: SystemCapabilities,
        speech_runtime: SpeechRuntime,
        avatar_runtime: AvatarRuntime,
    ) -> None:
        self.config = config
        self.capabilities = capabilities
        self.speech_runtime = speech_runtime
        self.avatar_runtime = avatar_runtime

    @property
    def profile(self) -> RuntimeProfile:
        profile = self.config.runtime_profile.strip().lower()
        if profile in PROFILE_SPECS:
            return profile  # type: ignore[return-value]
        return "safe_fallback"

    def plan(self) -> ModelRuntimePlan:
        spec = PROFILE_SPECS[self.profile]
        errors = self._validation_errors(spec)
        return ModelRuntimePlan(
            profile=spec.name,
            status="ready" if not errors else "degraded",
            budget=spec.budget,
            validation_errors=errors,
            components=self.components(),
        )

    def components(self) -> list[RuntimeComponent]:
        spec = PROFILE_SPECS[self.profile]
        speech = self.speech_runtime.status()
        avatar = self.avatar_runtime.status()
        return [
            RuntimeComponent(
                id="core-local",
                kind="core",
                status="ready",
                detail="本地 Core 服务已启动",
                required=True,
            ),
            self._llm_component(spec),
            self._speech_component("stt-local", "stt", self.config.stt_model, spec, speech),
            self._speech_component("tts-local", "tts", self.config.tts_model, spec, speech),
            RuntimeComponent(
                id="avatar-local",
                kind="avatar",
                status="ready" if avatar.renderer != "static_fallback" else "degraded",
                detail=(
                    "状态视频资源可用"
                    if avatar.renderer != "static_fallback"
                    else "尚未安装状态视频或局部口型运行时"
                ),
                required=False,
            ),
        ]

    def model_metadata(self) -> dict[str, tuple[str, ComponentStatus, dict[str, object]]]:
        spec = PROFILE_SPECS[self.profile]
        speech = self.speech_runtime.status()
        components = {item.id: item for item in self.components()}
        return {
            "llm-local": (
                "openai-compatible",
                components["llm-local"].status,
                {"profile": self.profile, "configured": bool(self.config.llm_base_url), "model": self.config.llm_model},
            ),
            "stt-local": (
                "speech-to-speech",
                components["stt-local"].status,
                {"profile": self.profile, "configured": speech.configured, "reachable": speech.reachable, "model": self.config.stt_model},
            ),
            "tts-local": (
                "speech-to-speech",
                components["tts-local"].status,
                {"profile": self.profile, "configured": speech.configured, "reachable": speech.reachable, "model": self.config.tts_model},
            ),
        }

    def _validation_errors(self, spec: ProfileSpec) -> list[str]:
        errors: list[str] = []
        if self.config.runtime_profile.strip().lower() not in PROFILE_SPECS:
            errors.append("invalid_runtime_profile")
        maximum_gpu_memory = max(
            (gpu.memory_mb for gpu in self.capabilities.gpus),
            default=0,
        )
        if maximum_gpu_memory < spec.gpu_memory_mb:
            errors.append("insufficient_gpu_memory")
        if self.capabilities.memory_gb < spec.system_memory_gb:
            errors.append("insufficient_system_memory")
        if spec.needs_llm_endpoint and not self.config.llm_base_url:
            errors.append("llm_not_configured")
        if spec.needs_voice and not self.speech_runtime.status().configured:
            errors.append("voice_not_configured")
        if spec.needs_voice and not self.config.stt_model.strip():
            errors.append("stt_model_not_configured")
        if spec.needs_voice and not self.config.tts_model.strip():
            errors.append("tts_model_not_configured")
        if spec.name == "quality_local" and "1.7b" in self.config.tts_model.lower():
            errors.append("tts_model_exceeds_quality_local_budget")
        if spec.name == "safe_fallback":
            errors.append("safe_fallback_active")
        return errors

    def _llm_component(self, spec: ProfileSpec) -> RuntimeComponent:
        if not self.config.llm_base_url:
            return RuntimeComponent(
                id="llm-local",
                kind="llm",
                status="unavailable",
                detail="尚未配置 OpenAI-compatible LLM 端点",
                required=spec.needs_llm_endpoint,
            )
        return RuntimeComponent(
            id="llm-local",
            kind="llm",
            status="ready",
            detail="OpenAI-compatible LLM 已配置，等待运行时健康检查",
            required=spec.needs_llm_endpoint,
        )

    def _speech_component(
        self,
        identifier: str,
        kind: Literal["stt", "tts"],
        model: str,
        spec: ProfileSpec,
        speech: SpeechRuntimeStatus,
    ) -> RuntimeComponent:
        if not model.strip():
            status: ComponentStatus = "unavailable"
            detail = "尚未配置模型 ID"
        elif speech.reachable:
            status = "ready"
            detail = "speech-to-speech Realtime 服务可连接"
        elif speech.configured:
            status = "degraded"
            detail = "Realtime 地址已配置，语音服务尚未监听"
        else:
            status = "unavailable"
            detail = "尚未配置 speech-to-speech Realtime 地址"
        return RuntimeComponent(
            id=identifier,
            kind=kind,
            status=status,
            detail=detail,
            required=spec.needs_voice,
        )
