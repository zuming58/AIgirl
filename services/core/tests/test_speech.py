import asyncio

from xinyu_core.speech import SpeechRuntime
from xinyu_core.speech import relay_voice_messages


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_speech_runtime_requires_an_explicit_endpoint() -> None:
    status = SpeechRuntime(None).status()

    assert status.configured is False
    assert status.reachable is False
    assert status.endpoint is None


def test_speech_runtime_rejects_non_websocket_urls() -> None:
    status = SpeechRuntime("http://127.0.0.1:8766/v1/realtime").status()

    assert status.configured is True
    assert status.reachable is False
    assert "格式无效" in status.detail


def test_speech_runtime_reports_reachable_websocket(
    monkeypatch,
) -> None:
    connection = FakeConnection()
    captured = {}

    def fake_connection(address, timeout):
        captured["address"] = address
        captured["timeout"] = timeout
        return connection

    monkeypatch.setattr(
        "xinyu_core.speech.socket.create_connection",
        fake_connection,
    )

    status = SpeechRuntime(
        "ws://127.0.0.1:8766/v1/realtime"
    ).status()

    assert status.reachable is True
    assert captured["address"] == ("127.0.0.1", 8766)
    assert captured["timeout"] == 0.35
    assert connection.closed is True


class FakeClientSocket:
    def __init__(self) -> None:
        self.messages = [
            {"type": "websocket.receive", "text": '{"type":"session.start"}'},
            {"type": "websocket.disconnect"},
        ]
        self.sent_text = []
        self.sent_bytes = []

    async def receive(self):
        await asyncio.sleep(0)
        return self.messages.pop(0)

    async def send_text(self, value):
        self.sent_text.append(value)

    async def send_bytes(self, value):
        self.sent_bytes.append(value)


class FakeUpstreamSocket:
    def __init__(self) -> None:
        self.sent = []
        self.replies = ['{"type":"response.audio.delta"}']

    async def send(self, value):
        self.sent.append(value)

    async def recv(self):
        if self.replies:
            return self.replies.pop(0)
        await asyncio.Future()


def test_voice_relay_preserves_realtime_text_messages() -> None:
    client = FakeClientSocket()
    upstream = FakeUpstreamSocket()

    asyncio.run(relay_voice_messages(client, upstream))

    assert upstream.sent == ['{"type":"session.start"}']
    assert client.sent_text == ['{"type":"response.audio.delta"}']
