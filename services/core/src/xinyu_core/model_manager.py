from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

import httpx

from .avatar import AvatarRuntime
from .config import AppConfig
from .contracts import (
    ModelRuntimeBudget,
    ModelProcessStatus,
    ModelRuntimePlan,
    RuntimeComponent,
    SystemCapabilities,
)
from .speech import SpeechRuntime, SpeechRuntimeStatus


RuntimeProfile = Literal["quality_local", "quality_cloud_llm", "safe_fallback"]
ComponentStatus = Literal["ready", "degraded", "unavailable", "disabled"]
ProcessState = Literal[
    "unregistered",
    "starting",
    "running",
    "stopping",
    "stopped",
    "failed",
]


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


@dataclass(frozen=True, slots=True)
class ProcessEvent:
    model_id: str
    state: ProcessState
    detail: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


ProcessFactory = Callable[[list[str]], Awaitable[Any]]
ProcessEventSink = Callable[[ProcessEvent], Awaitable[None] | None]


async def _spawn_process(command: list[str]) -> Any:
    return await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


class ManagedModelProcess:
    """Lifecycle wrapper with isolated failure and restart state."""

    def __init__(
        self,
        model_id: str,
        command: list[str],
        factory: ProcessFactory = _spawn_process,
        event_sink: ProcessEventSink | None = None,
        stop_timeout: float = 2.0,
    ) -> None:
        self.model_id = model_id
        self.command = command
        self.factory = factory
        self.event_sink = event_sink
        self.stop_timeout = stop_timeout
        self.state: ProcessState = "unregistered"
        self.pid: int | None = None
        self.restart_count = 0
        self.last_error: str | None = None
        self._process: Any | None = None
        self._watch_task: asyncio.Task[None] | None = None

    def status(self) -> ModelProcessStatus:
        return ModelProcessStatus(
            id=self.model_id,
            state=self.state,
            pid=self.pid,
            restart_count=self.restart_count,
            last_error=self.last_error,
        )

    async def _emit(self, detail: str | None = None) -> None:
        if self.event_sink is None:
            return
        result = self.event_sink(ProcessEvent(self.model_id, self.state, detail))
        if asyncio.iscoroutine(result):
            await result

    async def start(self) -> ModelProcessStatus:
        if self.state == "running":
            return self.status()
        self.state = "starting"
        self.last_error = None
        await self._emit()
        try:
            self._process = await self.factory(self.command)
            self.pid = getattr(self._process, "pid", None)
            self.state = "running"
            self._watch_task = asyncio.create_task(self._watch())
            await self._emit()
        except Exception as error:
            self.state = "failed"
            self.last_error = f"start_failed:{type(error).__name__}"
            await self._emit(self.last_error)
        return self.status()

    async def _watch(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            return_code = await process.wait()
        except asyncio.CancelledError:
            return
        except Exception as error:
            self.state = "failed"
            self.last_error = f"wait_failed:{type(error).__name__}"
            await self._emit(self.last_error)
            return
        if self.state in {"stopping", "stopped"}:
            return
        if return_code == 0:
            self.state = "stopped"
            await self._emit("process_exited")
        else:
            self.state = "failed"
            self.last_error = f"process_exit:{return_code}"
            await self._emit(self.last_error)

    async def stop(self) -> ModelProcessStatus:
        if self._process is None or self.state in {"stopped", "unregistered"}:
            self.state = "stopped"
            await self._emit()
            return self.status()
        self.state = "stopping"
        await self._emit()
        process = self._process
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=self.stop_timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
        finally:
            self.state = "stopped"
            self._process = None
            self.pid = None
            await self._emit()
        return self.status()

    async def restart(self) -> ModelProcessStatus:
        self.restart_count += 1
        await self.stop()
        return await self.start()


class ModelProcessSupervisor:
    def __init__(self, event_sink: ProcessEventSink | None = None) -> None:
        self.event_sink = event_sink
        self._processes: dict[str, ManagedModelProcess] = {}

    def register(
        self,
        model_id: str,
        command: list[str],
        *,
        factory: ProcessFactory = _spawn_process,
        stop_timeout: float = 2.0,
    ) -> ManagedModelProcess:
        process = ManagedModelProcess(
            model_id,
            command,
            factory=factory,
            event_sink=self.event_sink,
            stop_timeout=stop_timeout,
        )
        self._processes[model_id] = process
        return process

    def statuses(self) -> list[ModelProcessStatus]:
        return [process.status() for process in self._processes.values()]

    async def start(self, model_id: str) -> ModelProcessStatus:
        return await self._processes[model_id].start()

    async def stop(self, model_id: str) -> ModelProcessStatus:
        return await self._processes[model_id].stop()

    async def restart(self, model_id: str) -> ModelProcessStatus:
        return await self._processes[model_id].restart()

    async def stop_all(self) -> None:
        await asyncio.gather(*(process.stop() for process in self._processes.values()))


class ModelManager:
    """Describe model readiness without owning model processes or weights."""

    def __init__(
        self,
        config: AppConfig,
        capabilities: SystemCapabilities,
        speech_runtime: SpeechRuntime,
        avatar_runtime: AvatarRuntime,
        process_supervisor: ModelProcessSupervisor | None = None,
    ) -> None:
        self.config = config
        self.capabilities = capabilities
        self.speech_runtime = speech_runtime
        self.avatar_runtime = avatar_runtime
        self.process_supervisor = process_supervisor or ModelProcessSupervisor()
        self._speech_health: SpeechRuntimeStatus | None = None
        self._llm_health: tuple[bool, str] | None = None
        self._health_checked_at: datetime | None = None

    def refresh(self) -> None:
        """Run bounded protocol checks and cache the result for status reads."""
        self._speech_health = self.speech_runtime.status()
        self._llm_health = self._check_llm()
        self._health_checked_at = datetime.now(timezone.utc)

    def _ensure_health(self) -> None:
        if (
            self._health_checked_at is None
            or (datetime.now(timezone.utc) - self._health_checked_at).total_seconds() > 5
        ):
            self.refresh()

    def _check_llm(self) -> tuple[bool, str]:
        if not self.config.llm_base_url:
            return False, "llm_not_configured"
        base_url = self.config.llm_base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {self.config.llm_api_key}"}
        if not self.config.llm_api_key:
            headers = {}
        try:
            with httpx.Client(timeout=0.75, follow_redirects=True) as client:
                response = client.get(f"{base_url}/models", headers=headers)
        except (httpx.HTTPError, OSError):
            return False, "llm_unreachable"
        if response.status_code in {401, 403}:
            return False, "llm_auth_failed"
        if response.status_code >= 400:
            return False, f"llm_http_{response.status_code}"
        return True, "ok"

    @property
    def profile(self) -> RuntimeProfile:
        profile = self.config.runtime_profile.strip().lower()
        if profile in PROFILE_SPECS:
            return profile  # type: ignore[return-value]
        return "safe_fallback"

    def plan(self) -> ModelRuntimePlan:
        self._ensure_health()
        spec = PROFILE_SPECS[self.profile]
        errors = self._validation_errors(spec)
        return ModelRuntimePlan(
            profile=spec.name,
            status="ready" if not errors else "degraded",
            budget=spec.budget,
            validation_errors=errors,
            components=self.components(),
            health_checked_at=self._health_checked_at,
            processes=self.process_supervisor.statuses(),
        )

    def components(self) -> list[RuntimeComponent]:
        self._ensure_health()
        spec = PROFILE_SPECS[self.profile]
        speech = self._speech_health or self.speech_runtime.status()
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
        self._ensure_health()
        speech = self._speech_health or self.speech_runtime.status()
        components = {item.id: item for item in self.components()}
        return {
            "llm-local": (
                "openai-compatible",
                components["llm-local"].status,
                {
                    "profile": self.profile,
                    "configured": bool(self.config.llm_base_url),
                    "model": self.config.llm_model,
                    "health": self._llm_health[1] if self._llm_health else "unchecked",
                },
            ),
            "stt-local": (
                "speech-to-speech",
                components["stt-local"].status,
                {
                    "profile": self.profile,
                    "configured": speech.configured,
                    "reachable": speech.reachable,
                    "model": self.config.stt_model,
                    "health": speech.detail,
                },
            ),
            "tts-local": (
                "speech-to-speech",
                components["tts-local"].status,
                {
                    "profile": self.profile,
                    "configured": speech.configured,
                    "reachable": speech.reachable,
                    "model": self.config.tts_model,
                    "health": speech.detail,
                },
            ),
        }

    def _validation_errors(self, spec: ProfileSpec) -> list[str]:
        self._ensure_health()
        errors: list[str] = []
        speech = self._speech_health or self.speech_runtime.status()
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
        elif spec.needs_llm_endpoint and self._llm_health and not self._llm_health[0]:
            errors.append(self._llm_health[1])
        if spec.needs_voice and not speech.configured:
            errors.append("voice_not_configured")
        elif spec.needs_voice and not speech.reachable:
            errors.append("voice_unreachable")
        if spec.needs_voice and not self.config.stt_model.strip():
            errors.append("stt_model_not_configured")
        if spec.needs_voice and not self.config.tts_model.strip():
            errors.append("tts_model_not_configured")
        if spec.name == "quality_local" and "1.7b" in self.config.tts_model.lower():
            errors.append("tts_model_exceeds_quality_local_budget")
        if spec.name == "safe_fallback":
            errors.append("safe_fallback_active")
        return errors

    def register_process(
        self,
        model_id: str,
        command: list[str],
        *,
        factory: ProcessFactory = _spawn_process,
        stop_timeout: float = 2.0,
    ) -> ManagedModelProcess:
        return self.process_supervisor.register(
            model_id,
            command,
            factory=factory,
            stop_timeout=stop_timeout,
        )

    async def start_process(self, model_id: str) -> ModelProcessStatus:
        return await self.process_supervisor.start(model_id)

    async def stop_process(self, model_id: str) -> ModelProcessStatus:
        return await self.process_supervisor.stop(model_id)

    async def restart_process(self, model_id: str) -> ModelProcessStatus:
        return await self.process_supervisor.restart(model_id)

    async def stop_all_processes(self) -> None:
        await self.process_supervisor.stop_all()

    def _llm_component(self, spec: ProfileSpec) -> RuntimeComponent:
        self._ensure_health()
        if not self.config.llm_base_url:
            return RuntimeComponent(
                id="llm-local",
                kind="llm",
                status="unavailable",
                detail="尚未配置 OpenAI-compatible LLM 端点",
                required=spec.needs_llm_endpoint,
            )
        healthy, detail_code = self._llm_health or (False, "llm_unchecked")
        return RuntimeComponent(
            id="llm-local",
            kind="llm",
            status="ready" if healthy else "degraded",
            detail=(
                "OpenAI-compatible LLM 健康检查通过"
                if healthy
                else f"OpenAI-compatible LLM 健康检查失败：{detail_code}"
            ),
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
        self._ensure_health()
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
