from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from .contracts import AvatarStateUpdate, AvatarStatus


AVATAR_STATES = (
    "idle",
    "listening",
    "thinking",
    "speaking",
    "smiling",
    "goodnight",
)


@dataclass(slots=True)
class AvatarRuntime:
    data_dir: Path
    character_id: str = "xinyu-main"
    _state: str = field(init=False, default="idle")
    _emotion: str = field(init=False, default="calm")
    _intensity: float = field(init=False, default=0.35)
    _lock: Lock = field(init=False, default_factory=Lock)

    def __post_init__(self) -> None:
        self.data_dir = self.data_dir.resolve()

    @property
    def asset_dir(self) -> Path:
        return self.data_dir / "avatar" / self.character_id

    def available_states(self) -> list[str]:
        return [
            state
            for state in AVATAR_STATES
            if (self.asset_dir / f"{state}.mp4").is_file()
        ]

    def asset_path(self, state: str) -> Path | None:
        if state not in AVATAR_STATES:
            return None
        candidate = (self.asset_dir / f"{state}.mp4").resolve()
        if candidate.parent != self.asset_dir.resolve() or not candidate.is_file():
            return None
        return candidate

    def status(self) -> AvatarStatus:
        available = self.available_states()
        renderer = (
            "video_state_library"
            if {"idle", "listening", "thinking", "speaking"}.issubset(available)
            else "static_fallback"
        )
        with self._lock:
            state = self._state
            emotion = self._emotion
            intensity = self._intensity
        return AvatarStatus(
            character_id=self.character_id,
            state=state,
            emotion=emotion,
            intensity=intensity,
            renderer=renderer,
            available_states=available,
            target_resolution="1920x1080",
            target_fps=25,
            fallback_reason=(
                None
                if renderer == "video_state_library"
                else "高质量人物状态视频尚未导入，当前使用经批准的静态场景。"
            ),
        )

    def set_state(self, value: AvatarStateUpdate) -> AvatarStatus:
        with self._lock:
            self._state = value.state
            self._emotion = value.emotion
            self._intensity = value.intensity
        return self.status()
