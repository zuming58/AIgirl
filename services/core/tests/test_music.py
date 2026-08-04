import wave
from pathlib import Path

from xinyu_core.config import AppConfig
from xinyu_core.database import Database
from xinyu_core.music import MusicLibrary
from xinyu_core.repository import Repository


def write_silent_wav(path: Path, seconds: float = 0.05) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(8_000 * seconds)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * frame_count)


def make_library(tmp_path: Path) -> tuple[MusicLibrary, Repository, Path, Path]:
    first = tmp_path / "music-a"
    second = tmp_path / "music-b"
    first.mkdir()
    second.mkdir()
    database = Database(tmp_path / "music.db")
    database.initialize()
    return MusicLibrary(database, (first, second)), Repository(database), first, second


def test_music_library_indexes_metadata_without_exposing_paths(tmp_path: Path) -> None:
    library, repository, first, _ = make_library(tmp_path)
    source = first / "周末乐队 - 晚风.wav"
    write_silent_wav(source)

    response = library.scan()

    assert response.status.status == "ready"
    assert response.status.track_count == 1
    track = response.tracks[0]
    assert track.title == "晚风"
    assert track.artist == "周末乐队"
    assert track.duration_seconds is not None
    assert library.audio_path(track.id) == source.resolve()
    assert str(tmp_path) not in response.model_dump_json()
    exported = repository.export_data().data["media_assets"]
    assert exported[0]["path"] == ""
    assert str(tmp_path) not in str(exported)


def test_music_library_recovers_moved_files_by_content_hash(tmp_path: Path) -> None:
    library, _, first, second = make_library(tmp_path)
    source = first / "原位置.wav"
    destination = second / "新位置.wav"
    write_silent_wav(source)
    original_id = library.scan().tracks[0].id

    source.rename(destination)
    rescanned = library.scan()

    assert len(rescanned.tracks) == 1
    assert rescanned.tracks[0].id == original_id
    assert rescanned.tracks[0].status == "available"
    assert library.audio_path(original_id) == destination.resolve()


def test_music_library_keeps_missing_record_with_recovery_hint(tmp_path: Path) -> None:
    library, _, first, _ = make_library(tmp_path)
    source = first / "会断开的歌.wav"
    write_silent_wav(source)
    track_id = library.scan().tracks[0].id

    source.unlink()
    rescanned = library.scan()

    assert rescanned.status.status == "degraded"
    assert rescanned.status.missing_count == 1
    assert rescanned.tracks[0].id == track_id
    assert rescanned.tracks[0].status == "missing"
    assert "重新扫描" in rescanned.tracks[0].recovery_hint
    assert library.audio_path(track_id) is None


def test_music_directories_require_a_json_string_array(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "music-a"
    second = tmp_path / "music-b"
    monkeypatch.setenv("XINYU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "XINYU_MUSIC_DIRECTORIES_JSON",
        f'["{first.as_posix()}", "{second.as_posix()}"]',
    )
    configured = AppConfig.from_env()

    assert configured.music_directories == (first.resolve(), second.resolve())

    monkeypatch.setenv("XINYU_MUSIC_DIRECTORIES_JSON", str(first))
    assert AppConfig.from_env().music_directories == ()
