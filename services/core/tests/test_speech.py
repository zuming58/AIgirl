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
    started_at = time.perf_counter() - 1
    tracker = VoiceLatencyTracker(started_at=started_at, session_id="session-1")

    for offset, event_type in enumerate(
        (
            "input_audio_buffer.speech_started",
            "conversation.item.input_audio_transcription.completed",
            "response.output_text.delta",
            "response.audio.delta",
            "response.cancelled",
        )
    ):
        tracker.observe(event_type, observed_at=started_at + offset * 0.1)

    metrics = tracker.snapshot()

    assert metrics.session_id == "session-1"
    assert metrics.turn_id is not None
    assert metrics.vad_ms is not None
    assert metrics.final_transcript_ms is not None
    assert metrics.first_token_ms is not None
    assert metrics.first_audio_ms is not None
    assert metrics.complete_ms is None
    assert metrics.interrupted_ms == 400.0
    assert metrics.turn_interruptions == 1
    assert metrics.interruptions == 1


def test_latency_tracker_resets_metrics_for_each_turn() -> None:
    tracker = VoiceLatencyTracker(started_at=10.0, session_id="session-1")

    first_turn = (
        ("input_audio_buffer.append", 10.0),
        ("input_audio_buffer.speech_started", 10.1),
        ("conversation.item.input_audio_transcription.completed", 10.2),
        ("response.created", 10.3),
        ("response.output_text.delta", 10.4),
        ("response.audio.delta", 10.5),
        ("response.done", 10.8),
    )
    for event_type, observed_at in first_turn:
        tracker.observe(event_type, observed_at=observed_at)
    first_metrics = tracker.snapshot()

    second_turn = (
        ("input_audio_buffer.append", 20.0),
        ("input_audio_buffer.speech_started", 20.2),
        ("conversation.item.input_audio_transcription.completed", 20.5),
        ("response.created", 20.7),
        ("response.output_text.delta", 21.1),
        ("response.audio.delta", 21.4),
        ("response.done", 22.0),
    )
    for event_type, observed_at in second_turn:
        tracker.observe(event_type, observed_at=observed_at)
    second_metrics = tracker.snapshot()

    assert second_metrics.session_id == first_metrics.session_id
    assert second_metrics.turn_id != first_metrics.turn_id
    assert first_metrics.vad_ms == 100.0
    assert first_metrics.first_token_ms == 400.0
    assert second_metrics.vad_ms == 200.0
    assert second_metrics.final_transcript_ms == 500.0
    assert second_metrics.first_token_ms == 1100.0
    assert second_metrics.first_audio_ms == 1400.0
    assert second_metrics.complete_ms == 2000.0


def test_latency_tracker_handles_text_only_out_of_order_and_cancelled_turns() -> None:
    tracker = VoiceLatencyTracker(started_at=1.0, session_id="session-1")

    tracker.observe("response.audio.delta", observed_at=2.0)
    tracker.observe("response.output_text.delta", observed_at=2.1)
    text_metrics = tracker.snapshot()
    tracker.observe("response.cancelled", observed_at=2.2)
    cancelled_metrics = tracker.snapshot()
    tracker.observe("response.created", observed_at=3.0)
    next_metrics = tracker.snapshot()

    assert text_metrics.first_audio_ms == 0.0
    assert text_metrics.first_token_ms == 100.0
    assert cancelled_metrics.interrupted_ms == 200.0
    assert cancelled_metrics.turn_interruptions == 1
    assert cancelled_metrics.interruptions == 1
    assert next_metrics.turn_id != cancelled_metrics.turn_id
    assert next_metrics.first_audio_ms is None
    assert next_metrics.first_token_ms is None
    assert next_metrics.interruptions == 1
    assert next_metrics.turn_interruptions == 0


def test_latency_tracker_starts_a_new_turn_when_user_interrupts_response() -> None:
    tracker = VoiceLatencyTracker(started_at=1.0, session_id="session-1")

    tracker.observe("response.created", observed_at=2.0)
    tracker.observe("response.audio.delta", observed_at=2.3)
    response_metrics = tracker.snapshot()
    tracker.observe("input_audio_buffer.append", observed_at=2.5)
    tracker.observe("input_audio_buffer.speech_started", observed_at=2.6)
    interruption_turn = tracker.snapshot()

    assert interruption_turn.turn_id != response_metrics.turn_id
    assert interruption_turn.first_audio_ms is None
    assert interruption_turn.vad_ms == 100.0


def test_latency_tracker_treats_a_second_response_created_as_a_new_turn() -> None:
    tracker = VoiceLatencyTracker(started_at=1.0, session_id="session-1")

    tracker.observe("response.created", observed_at=2.0)
    tracker.observe("response.output_text.delta", observed_at=2.2)
    first_turn = tracker.snapshot()
    tracker.observe("response.created", observed_at=3.0)
    second_turn = tracker.snapshot()

    assert second_turn.turn_id != first_turn.turn_id
    assert second_turn.first_token_ms is None
    assert second_turn.interruptions == 0


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
