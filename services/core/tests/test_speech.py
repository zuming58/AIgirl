import asyncio
import time

from xinyu_core.speech import SpeechRuntime, VoiceLatencyTracker
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


def test_speech_runtime_requires_a_successful_websocket_handshake(monkeypatch) -> None:
    class HandshakeConnection(FakeConnection):
        def sendall(self, value) -> None:
            self.request = value

        def recv(self, size) -> bytes:
            return b"HTTP/1.1 503 Service Unavailable\r\n\r\n"

    monkeypatch.setattr(
        "xinyu_core.speech.socket.create_connection",
        lambda *args, **kwargs: HandshakeConnection(),
    )

    status = SpeechRuntime("ws://127.0.0.1:8766/v1/realtime").status()

    assert status.configured is True
    assert status.reachable is False
    assert "握手" in status.detail


def test_latency_tracker_records_protocol_milestones() -> None:
    tracker = VoiceLatencyTracker(started_at=time.perf_counter() - 1)

    for event_type in (
        "input_audio_buffer.speech_started",
        "conversation.item.input_audio_transcription.completed",
        "response.output_text.delta",
        "response.audio.delta",
        "response.done",
        "response.cancelled",
    ):
        tracker.observe(event_type)

    metrics = tracker.snapshot()

    assert metrics.vad_ms is not None
    assert metrics.final_transcript_ms is not None
    assert metrics.first_token_ms is not None
    assert metrics.first_audio_ms is not None
    assert metrics.complete_ms is not None
    assert metrics.interruptions == 1


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


def test_voice_relay_forwards_text_audio_and_interruption_metrics() -> None:
    class StreamingClient:
        def __init__(self) -> None:
            self.sent_text = []
            self.release = asyncio.Event()
            self.input_sent = False

        async def receive(self):
            if not self.input_sent:
                self.input_sent = True
                return {"type": "websocket.receive", "text": '{"type":"input_audio_buffer.append"}'}
            await self.release.wait()
            return {"type": "websocket.disconnect"}

        async def send_text(self, value):
            self.sent_text.append(value)
            if len(self.sent_text) == 3:
                self.release.set()

        async def send_bytes(self, value):
            raise AssertionError("the simulated upstream should send text frames here")

    class StreamingUpstream:
        def __init__(self) -> None:
            self.sent = []
            self.ready = asyncio.Event()
            self.replies = [
                '{"type":"response.output_text.delta","delta":"你好"}',
                '{"type":"response.audio.delta","delta":"audio"}',
                '{"type":"response.cancelled"}',
            ]

        async def send(self, value):
            self.sent.append(value)
            self.ready.set()

        async def recv(self):
            await self.ready.wait()
            if self.replies:
                return self.replies.pop(0)
            await asyncio.Future()

    async def exercise():
        client = StreamingClient()
        upstream = StreamingUpstream()
        events = []

        await relay_voice_messages(
            client,
            upstream,
            on_event=lambda event_type, metrics: events.append(
                (event_type, metrics)
            ),
        )
        assert upstream.sent == ['{"type":"input_audio_buffer.append"}']
        assert [event[0] for event in events] == [
            "response.output_text.delta",
            "response.audio.delta",
            "response.cancelled",
        ]
        assert events[-1][1].interruptions == 1

    asyncio.run(exercise())
