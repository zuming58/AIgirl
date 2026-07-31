from pathlib import Path

from xinyu_core.avatar import AvatarRuntime
from xinyu_core.contracts import AvatarStateUpdate


def test_avatar_runtime_is_honest_until_state_assets_exist(tmp_path: Path) -> None:
    runtime = AvatarRuntime(tmp_path)

    status = runtime.status()
    assert status.renderer == "static_fallback"
    assert status.available_states == []
    assert status.fallback_reason

    changed = runtime.set_state(
        AvatarStateUpdate(
            state="thinking",
            emotion="attentive",
            intensity=0.6,
        )
    )
    assert changed.state == "thinking"
    assert changed.emotion == "attentive"


def test_avatar_runtime_detects_a_complete_video_state_library(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "avatar" / "xinyu-main"
    asset_dir.mkdir(parents=True)
    for state in ("idle", "listening", "thinking", "speaking"):
        (asset_dir / f"{state}.mp4").write_bytes(b"video-placeholder")

    status = AvatarRuntime(tmp_path).status()
    assert status.renderer == "video_state_library"
    assert set(status.available_states) == {
        "idle",
        "listening",
        "thinking",
        "speaking",
    }
    assert status.fallback_reason is None
