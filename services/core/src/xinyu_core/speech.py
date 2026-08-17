from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class SpeechRuntimeStatus:
    configured: bool
    reachable: bool
    endpoint: str | None
    detail: str


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
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        try:
            connection = socket.create_connection(
                (parsed.hostname, port),
                timeout=0.35,
            )
            connection.close()
        except OSError:
            return SpeechRuntimeStatus(
                configured=True,
                reachable=False,
                endpoint=self.realtime_url,
                detail="speech-to-speech 服务未监听",
            )
        return SpeechRuntimeStatus(
            configured=True,
            reachable=True,
            endpoint=self.realtime_url,
            detail="speech-to-speech Realtime 服务可连接",
        )


async def relay_voice_messages(client: Any, upstream: Any) -> None:
    async def client_to_upstream() -> None:
        while True:
            message = await client.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await upstream.send(message["bytes"])
            elif message.get("text") is not None:
                await upstream.send(message["text"])

    async def upstream_to_client() -> None:
        while True:
            message = await upstream.recv()
            if isinstance(message, bytes):
                await client.send_bytes(message)
            else:
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
