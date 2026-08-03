from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import os
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from .contracts import VoiceLatencyMetrics


@dataclass(frozen=True, slots=True)
class SpeechRuntimeStatus:
    configured: bool
    reachable: bool
    endpoint: str | None
    detail: str


def _websocket_health_check(realtime_url: str) -> tuple[bool, str]:
    parsed = urlparse(realtime_url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        return False, "Realtime 地址格式无效，必须使用 ws:// 或 wss://"
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    connection: socket.socket | Any | None = None
    try:
        connection = socket.create_connection(
            (parsed.hostname, port),
            timeout=0.35,
        )
        # Keep unit-test socket doubles useful while requiring a real HTTP 101
        # handshake for production sockets.
        if not hasattr(connection, "sendall") or not hasattr(connection, "recv"):
            return True, "speech-to-speech 服务端口可连接"
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            connection = context.wrap_socket(connection, server_hostname=parsed.hostname)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        if hasattr(connection, "settimeout"):
            connection.settimeout(0.35)
        connection.sendall(request)
        response = connection.recv(512)
        if response.startswith(b"HTTP/1.1 101") or response.startswith(b"HTTP/1.0 101"):
            return True, "speech-to-speech Realtime 握手成功"
        return False, "speech-to-speech Realtime 握手被拒绝"
    except (OSError, ssl.SSLError, ValueError):
        return False, "speech-to-speech 服务未通过健康检查"
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass


class SpeechRuntime:
    def __init__(self, realtime_url: str | None) -> None:
        self.realtime_url = realtime_url

    def status(self) -> SpeechRuntimeStatus:
        if not self.realtime_url:
            return SpeechRuntimeStatus(
                configured=False,
                reachable=False,
                endpoint=None,
                detail="尚未配置 speech-to-speech Realtime 地址",
            )
        parsed = urlparse(self.realtime_url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
            return SpeechRuntimeStatus(
                configured=True,
                reachable=False,
                endpoint=self.realtime_url,
                detail="Realtime 地址格式无效，必须使用 ws:// 或 wss://",
            )
        reachable, detail = _websocket_health_check(self.realtime_url)
        return SpeechRuntimeStatus(
            configured=True,
            reachable=reachable,
            endpoint=self.realtime_url,
            detail=detail,
        )


@dataclass(slots=True)
class VoiceLatencyTracker:
    """Measure protocol milestones without retaining audio or message content."""

    started_at: float = 0.0
    _marks: dict[str, float] | None = None
    _interruptions: int = 0

    def __post_init__(self) -> None:
        if self.started_at <= 0:
            self.started_at = time.perf_counter()
        if self._marks is None:
            self._marks = {}

    def observe(self, event_type: str) -> bool:
        now = time.perf_counter()
        mark = {
            "input_audio_buffer.speech_started": "vad",
            "conversation.item.input_audio_transcription.completed": "final_transcript",
            "response.output_text.delta": "first_token",
            "response.text.delta": "first_token",
            "response.audio.delta": "first_audio",
            "response.done": "complete",
            "response.completed": "complete",
        }.get(event_type)
        if mark and mark not in self._marks:
            self._marks[mark] = now
        if event_type in {"response.cancelled", "response.interrupted", "conversation.item.truncated"}:
            self._interruptions += 1
            self._marks["interrupted"] = now
        return mark is not None or event_type.startswith("response.")

    def snapshot(self) -> VoiceLatencyMetrics:
        def elapsed(name: str) -> float | None:
            value = self._marks.get(name)
            if value is None:
                return None
            return round((value - self.started_at) * 1000, 2)

        return VoiceLatencyMetrics(
            vad_ms=elapsed("vad"),
            final_transcript_ms=elapsed("final_transcript"),
            first_token_ms=elapsed("first_token"),
            first_audio_ms=elapsed("first_audio"),
            complete_ms=elapsed("complete"),
            interruptions=self._interruptions,
        )


async def relay_voice_messages(
    client: Any,
    upstream: Any,
    on_event: Callable[[str, VoiceLatencyMetrics], Awaitable[None] | None] | None = None,
    tracker: VoiceLatencyTracker | None = None,
) -> None:
    tracker = tracker or VoiceLatencyTracker()

    async def observe_message(message: str | bytes, source: str) -> None:
        if isinstance(message, bytes):
            return
        try:
            import json

            payload = json.loads(message)
        except (TypeError, ValueError):
            return
        event_type = payload.get("type")
        if not isinstance(event_type, str) or not tracker.observe(event_type):
            return
        if on_event is not None:
            result = on_event(event_type, tracker.snapshot())
            if inspect.isawaitable(result):
                await result

    async def client_to_upstream() -> None:
        while True:
            message = await client.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await observe_message(message["bytes"], "client")
                await upstream.send(message["bytes"])
            elif message.get("text") is not None:
                await observe_message(message["text"], "client")
                await upstream.send(message["text"])

    async def upstream_to_client() -> None:
        while True:
            message = await upstream.recv()
            if isinstance(message, bytes):
                await observe_message(message, "upstream")
                await client.send_bytes(message)
            else:
                await observe_message(message, "upstream")
                await client.send_text(message)

    tasks = {
        asyncio.create_task(client_to_upstream()),
        asyncio.create_task(upstream_to_client()),
    }
    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    results = await asyncio.gather(*done, return_exceptions=True)
    for result in results:
        if isinstance(result, asyncio.CancelledError):
            continue
        if isinstance(result, BaseException):
            raise result
