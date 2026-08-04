from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from mutagen import File as MutagenFile

from .contracts import MusicLibraryResponse, MusicLibraryStatus, MusicTrackRecord
from .database import Database, iso_now


AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}


def _first(tags: Any, *names: str) -> str | None:
    if tags is None:
        return None
    for name in names:
        value = tags.get(name)
        if isinstance(value, list) and value:
            value = value[0]
        if value is not None and str(value).strip():
            return str(value).strip()[:500]
    return None


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _has_cover(path: Path) -> bool:
    audio = MutagenFile(path, easy=False)
    tags = getattr(audio, "tags", None)
    if tags is None:
        return False
    keys = {str(key).lower() for key in tags.keys()}
    return any(
        key.startswith("apic")
        or key in {"covr", "metadata_block_picture"}
        for key in keys
    )


class MusicLibrary:
    def __init__(self, database: Database, directories: tuple[Path, ...]) -> None:
        self.database = database
        self.directories = directories

    def scan(self) -> MusicLibraryResponse:
        if not self.directories:
            return self.list()
        roots = [path for path in self.directories if path.is_dir()]
        seen: set[str] = set()
        scan_at = iso_now()
        with self.database.connect() as connection:
            for root in roots:
                for candidate in root.rglob("*"):
                    if not candidate.is_file() or candidate.suffix.lower() not in AUDIO_EXTENSIONS:
                        continue
                    path = candidate.resolve()
                    if not path.is_relative_to(root.resolve()):
                        continue
                    fingerprint = _fingerprint(path)
                    audio = MutagenFile(path, easy=True)
                    tags = getattr(audio, "tags", None)
                    stem_artist, separator, stem_title = path.stem.partition(" - ")
                    title = _first(tags, "title") or (stem_title if separator else path.stem)
                    artist = _first(tags, "artist", "albumartist") or (
                        stem_artist if separator else None
                    )
                    album = _first(tags, "album")
                    length = getattr(getattr(audio, "info", None), "length", None)
                    metadata = {
                        "title": title[:500],
                        "artist": artist[:500] if artist else None,
                        "album": album[:500] if album else None,
                        "duration_seconds": round(float(length), 3) if length else None,
                        "status": "available",
                        "cover_available": _has_cover(path),
                        "last_scan_at": scan_at,
                    }
                    row = connection.execute(
                        "SELECT id FROM media_assets WHERE kind='music' AND sha256=?",
                        (fingerprint,),
                    ).fetchone()
                    asset_id = row["id"] if row else str(uuid4())
                    connection.execute(
                        """
                        INSERT INTO media_assets(id, kind, path, sha256, metadata_json, created_at)
                        VALUES(?, 'music', ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            path=excluded.path, sha256=excluded.sha256,
                            metadata_json=excluded.metadata_json
                        """,
                        (asset_id, str(path), fingerprint, json.dumps(metadata, ensure_ascii=False), scan_at),
                    )
                    seen.add(asset_id)
            rows = connection.execute(
                "SELECT id, metadata_json FROM media_assets WHERE kind='music'"
            ).fetchall()
            for row in rows:
                if row["id"] in seen:
                    continue
                metadata = json.loads(row["metadata_json"] or "{}")
                metadata.update(
                    {
                        "status": "missing",
                        "last_scan_at": scan_at,
                        "recovery_hint": "文件已断开；放回任一音乐目录并重新扫描即可恢复。",
                    }
                )
                connection.execute(
                    "UPDATE media_assets SET metadata_json=? WHERE id=?",
                    (json.dumps(metadata, ensure_ascii=False), row["id"]),
                )
        return self.list()

    def list(self) -> MusicLibraryResponse:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, path, metadata_json FROM media_assets WHERE kind='music' ORDER BY created_at"
            ).fetchall()
        tracks: list[MusicTrackRecord] = []
        last_scan: datetime | None = None
        for row in rows:
            metadata = json.loads(row["metadata_json"] or "{}")
            available = Path(row["path"]).is_file() and metadata.get("status") != "missing"
            scanned = metadata.get("last_scan_at")
            if scanned:
                parsed = datetime.fromisoformat(scanned)
                if last_scan is None or parsed > last_scan:
                    last_scan = parsed
            tracks.append(
                MusicTrackRecord(
                    id=row["id"],
                    title=metadata.get("title") or "未知曲目",
                    artist=metadata.get("artist"),
                    album=metadata.get("album"),
                    duration_seconds=metadata.get("duration_seconds"),
                    status="available" if available else "missing",
                    cover_available=bool(metadata.get("cover_available")),
                    recovery_hint=None if available else metadata.get("recovery_hint") or "文件不可用，请重新扫描音乐目录。",
                )
            )
        missing = sum(track.status == "missing" for track in tracks)
        configured = bool(self.directories)
        return MusicLibraryResponse(
            status=MusicLibraryStatus(
                configured=configured,
                status="disabled" if not configured else ("degraded" if missing else "ready"),
                track_count=len(tracks),
                missing_count=missing,
                last_scan_at=last_scan,
                error_code=None if configured else "music_library_not_configured",
            ),
            tracks=tracks,
        )

    def audio_path(self, asset_id: str) -> Path | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT path FROM media_assets WHERE id=? AND kind='music'",
                (asset_id,),
            ).fetchone()
        if not row:
            return None
        candidate = Path(row["path"])
        return candidate if candidate.is_file() else None
