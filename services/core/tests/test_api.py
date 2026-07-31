import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from xinyu_core.app import create_app
from xinyu_core.config import AppConfig
from xinyu_core.contracts import PlanCreate


class FailingProvider:
    id = "failing-test-provider"

    async def reply(self, *args, **kwargs) -> str:
        raise RuntimeError("simulated provider outage")


def make_client(tmp_path: Path) -> TestClient:
    config = AppConfig(
        data_dir=tmp_path,
        database_path=tmp_path / "xinyu.db",
    )
    return TestClient(create_app(config))


def test_health_runtime_and_models(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/health").json()["status"] == "ok"
        runtime = client.get("/v1/runtime/status").json()
        assert runtime["status"] == "degraded"
        assert any(item["kind"] == "llm" for item in runtime["components"])
        capabilities = client.get("/v1/system/capabilities").json()
        assert capabilities["logical_cores"] >= 1
        assert capabilities["recommended_profile"] in {
            "high_quality_24gb",
            "high_quality_16gb",
            "balanced_10gb",
            "cpu_compatibility",
        }
        assert len(client.get("/v1/models").json()) >= 5
        avatar = client.get("/v1/avatar/status").json()
        assert avatar["renderer"] == "static_fallback"
        changed = client.post(
            "/v1/avatar/state",
            json={
                "state": "listening",
                "emotion": "attentive",
                "intensity": 0.5,
            },
        ).json()
        assert changed["state"] == "listening"


def test_complete_avatar_state_library_is_served_as_local_media(
    tmp_path: Path,
) -> None:
    avatar_directory = tmp_path / "avatar" / "xinyu-main"
    avatar_directory.mkdir(parents=True)
    for state in ("idle", "listening", "thinking", "speaking"):
        (avatar_directory / f"{state}.mp4").write_bytes(
            f"demo-{state}".encode()
        )

    with make_client(tmp_path) as client:
        status = client.get("/v1/avatar/status").json()
        assert status["renderer"] == "video_state_library"
        assert set(status["available_states"]) == {
            "idle",
            "listening",
            "thinking",
            "speaking",
        }
        asset = client.get("/v1/avatar/assets/idle")
        assert asset.status_code == 200
        assert asset.headers["content-type"] == "video/mp4"
        assert asset.content == b"demo-idle"
        assert client.get("/v1/avatar/assets/unknown").status_code == 404


def test_chat_persists_messages_and_explicit_memory(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "请记住我喜欢少糖拿铁"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "development-fallback"
        assert len(body["memory_candidates"]) == 1

        messages = client.get(
            f"/v1/conversations/{body['session_id']}/messages"
        ).json()
        assert [item["role"] for item in messages] == ["user", "assistant"]
        conversations = client.get("/v1/conversations").json()
        assert conversations[0]["id"] == body["session_id"]
        assert conversations[0]["message_count"] == 2
        assert conversations[0]["last_message"] == body["reply"]

        memories = client.post(
            "/v1/memories/query", json={"query": "拿铁"}
        ).json()
        assert memories[0]["user_confirmed"] is True
        context = client.get(
            f"/v1/memories/{memories[0]['id']}/context"
        ).json()
        assert "明确希望我记住" in context["explanation"]
        assert context["source_message"]["content"] == "请记住我喜欢少糖拿铁"

        diagnostics = client.get("/v1/diagnostics")
        assert diagnostics.status_code == 200
        report = diagnostics.json()
        assert report["counts"]["messages"] == 2
        assert report["counts"]["memories"] == 1
        assert report["database"]["schema_version"] == 1
        assert report["privacy"]["contains_private_content"] is False
        assert "少糖拿铁" not in diagnostics.text
        assert str(tmp_path) not in diagnostics.text


def test_plan_persona_mood_and_export(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        plan = client.post("/v1/plans", json={"title": "晚上散步"}).json()
        completed = client.patch(
            f"/v1/plans/{plan['id']}", json={"status": "completed"}
        ).json()
        assert completed["progress"] == 1

        persona = client.put(
            "/v1/persona",
            json={
                "name": "心屿",
                "relationship_role": "companion",
                "background": "温暖、尊重边界。",
            },
        ).json()
        assert persona["version"] == 2

        mood = client.post(
            "/v1/mood",
            json={
                "valence": 0.7,
                "arousal": 0.3,
                "energy": 0.6,
                "closeness": 0.8,
                "stress": 0.1,
                "reason": "conversation",
            },
        ).json()
        assert mood["closeness"] == 0.8
        assert client.get("/v1/data/export").json()["schema_version"] == 1


def test_settings_voice_and_data_lifecycle(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        update = client.put(
            "/v1/settings/privacy.memory_enabled",
            json={"value": False},
        )
        assert update.status_code == 200
        assert update.json()["value"] is False
        assert (
            client.get("/v1/settings").json()["privacy.memory_enabled"] is False
        )

        voice = client.post("/v1/voice/session")
        assert voice.status_code == 200
        assert voice.json()["status"] == "degraded"
        assert voice.json()["provider"] == "speech-to-speech"
        assert voice.json()["endpoint"] == "/v1/realtime/voice"

        plan = client.post("/v1/plans", json={"title": "测试清除"}).json()
        assert client.delete(f"/v1/plans/{plan['id']}").status_code == 204

        client.post("/v1/plans", json={"title": "稍后会被清除"})
        backup = client.post("/v1/data/backups")
        assert backup.status_code == 201
        assert backup.json()["name"].endswith(".db")
        assert backup.json()["size_bytes"] > 0
        assert len(client.get("/v1/data/backups").json()) == 1
        assert client.delete("/v1/data").status_code == 204
        assert len(client.get("/v1/data/backups").json()) == 2
        assert client.get("/v1/plans").json() == []
        assert (
            client.get("/v1/settings").json()["privacy.memory_enabled"] is True
        )


def test_voice_transcripts_are_persisted_idempotently_and_extract_memory(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        session = client.post("/v1/voice/session").json()
        payload = {
            "session_id": session["session_id"],
            "transcript_id": "input-item-1",
            "role": "user",
            "content": "请记住我喜欢桂花拿铁",
            "metadata": {"source": "speech-to-speech"},
        }
        first = client.post("/v1/voice/transcripts", json=payload)
        duplicate = client.post("/v1/voice/transcripts", json=payload)

        assert first.status_code == 200
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == first.json()["id"]
        assert first.json()["metadata"]["voice_transcript_id"] == "input-item-1"

        assistant = client.post(
            "/v1/voice/transcripts",
            json={
                "session_id": session["session_id"],
                "transcript_id": "response-1",
                "role": "assistant",
                "content": "好呀，我会记得。",
            },
        )
        assert assistant.status_code == 200
        messages = client.get(
            f"/v1/conversations/{session['session_id']}/messages"
        ).json()
        assert [message["role"] for message in messages] == ["user", "assistant"]

        memories = client.post(
            "/v1/memories/query",
            json={"query": "桂花拿铁"},
        ).json()
        assert len(memories) == 1
        assert memories[0]["source_message_id"] == first.json()["id"]


def test_backup_restore_requires_confirmation_and_is_reversible(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        client.post("/v1/plans", json={"title": "备份前的计划"})
        backup = client.post("/v1/data/backups").json()
        client.post("/v1/plans", json={"title": "备份后的计划"})

        endpoint = f"/v1/data/backups/{backup['name']}/restore"
        assert (
            client.post(endpoint, json={"confirmed": False}).status_code
            == 400
        )
        restored = client.post(endpoint, json={"confirmed": True})
        assert restored.status_code == 200
        assert restored.json()["restored_from"] == backup["name"]
        assert restored.json()["safety_backup"]["name"] != backup["name"]

        plans = client.get("/v1/plans").json()
        assert [item["title"] for item in plans] == ["备份前的计划"]
        assert len(client.get("/v1/data/backups").json()) == 2


def test_json_export_can_be_safely_imported(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.post("/v1/plans", json={"title": "导出时已有"})
        exported = client.get("/v1/data/export").json()
        client.post("/v1/plans", json={"title": "导出后新增"})

        assert (
            client.post(
                "/v1/data/import",
                json={**exported, "confirmed": False},
            ).status_code
            == 400
        )
        imported = client.post(
            "/v1/data/import",
            json={**exported, "confirmed": True},
        )
        assert imported.status_code == 200
        assert imported.json()["imported_rows"] > 0
        assert imported.json()["safety_backup"]["size_bytes"] > 0
        assert [
            item["title"] for item in client.get("/v1/plans").json()
        ] == ["导出时已有"]

        incompatible = {
            **exported,
            "schema_version": 999,
            "confirmed": True,
        }
        assert client.post("/v1/data/import", json=incompatible).status_code == 422


def test_websocket_announces_runtime(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        with client.websocket_connect("/v1/app/events") as websocket:
            event = websocket.receive_json()
            assert event["type"] == "runtime.ready"
            assert event["payload"]["version"] == "0.1.0"


def test_voice_websocket_exposes_an_honest_degraded_contract(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        with client.websocket_connect("/v1/realtime/voice") as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "voice.session.ready"
            assert ready["payload"]["status"] == "degraded"
            assert ready["payload"]["missing_components"] == ["stt", "tts"]

            websocket.send_json({"type": "session.start"})
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "voice_runtime_unavailable"
            assert error["payload"]["recoverable"] is True


def test_voice_websocket_relays_to_a_reachable_upstream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class StatusConnection:
        def close(self) -> None:
            pass

    class Upstream:
        def __init__(self) -> None:
            self.sent = []
            self.received = asyncio.Event()
            self.replied = False

        async def send(self, value) -> None:
            self.sent.append(value)
            self.received.set()

        async def recv(self):
            await self.received.wait()
            if not self.replied:
                self.replied = True
                return '{"type":"response.audio.delta","delta":"demo"}'
            await asyncio.Future()

    class UpstreamContext:
        def __init__(self, upstream) -> None:
            self.upstream = upstream

        async def __aenter__(self):
            return self.upstream

        async def __aexit__(self, *args):
            return False

    upstream = Upstream()
    monkeypatch.setattr(
        "xinyu_core.speech.socket.create_connection",
        lambda *args, **kwargs: StatusConnection(),
    )
    monkeypatch.setattr(
        "xinyu_core.app.websocket_connect",
        lambda *args, **kwargs: UpstreamContext(upstream),
    )
    config = AppConfig(
        data_dir=tmp_path,
        database_path=tmp_path / "voice-proxy.db",
        speech_realtime_url="ws://127.0.0.1:8766/v1/realtime",
    )

    with TestClient(create_app(config)) as client:
        with client.websocket_connect("/v1/realtime/voice") as websocket:
            ready = websocket.receive_json()
            assert ready["payload"]["status"] == "ready"
            websocket.send_text('{"type":"input_audio_buffer.append"}')
            reply = websocket.receive_json()
            assert reply["type"] == "response.audio.delta"

    assert upstream.sent == ['{"type":"input_audio_buffer.append"}']


def test_chat_degrades_cleanly_when_configured_provider_fails(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        client.app.state.chat_service.provider = FailingProvider()
        response = client.post("/v1/chat", json={"message": "今晚有点累"})

        assert response.status_code == 200
        assert response.json()["provider"] == "development-fallback"

        llm = next(
            item
            for item in client.get("/v1/models").json()
            if item["id"] == "llm-local"
        )
        assert llm["status"] == "degraded"
        assert llm["metadata"]["last_error"] == "RuntimeError"

        exported_turns = client.get("/v1/data/export").json()["data"]["turns"]
        assert exported_turns[-1]["status"] == "completed"


def test_local_token_is_enforced(tmp_path: Path) -> None:
    config = AppConfig(
        data_dir=tmp_path,
        database_path=tmp_path / "secure.db",
        auth_token="secret",
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/health").status_code == 401
        assert (
            client.get(
                "/health", headers={"Authorization": "Bearer secret"}
            ).status_code
            == 200
        )
        avatar_directory = tmp_path / "avatar" / "xinyu-main"
        avatar_directory.mkdir(parents=True, exist_ok=True)
        (avatar_directory / "idle.mp4").write_bytes(b"avatar")
        assert client.get("/v1/avatar/assets/idle").status_code == 401
        assert (
            client.get("/v1/avatar/assets/idle?token=secret").status_code
            == 200
        )


def test_notification_inbox_preserves_and_acknowledges_missed_reminders(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        repository = client.app.state.repository
        now = datetime.now(timezone.utc)
        repository.create_plan(
            PlanCreate(
                title="测试持久提醒",
                reminder_at=now - timedelta(seconds=1),
            )
        )
        claimed = repository.claim_due_plan_reminders(now)
        assert len(claimed) == 1
        repository.mark_proactive_event_delivered(claimed[0]["event_id"])

        inbox = client.get("/v1/notifications").json()
        assert len(inbox) == 1
        assert inbox[0]["payload"]["task"]["title"] == "测试持久提醒"

        acknowledged = client.post(
            f"/v1/notifications/{inbox[0]['id']}/acknowledge"
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "acknowledged"
        assert client.get("/v1/notifications").json() == []
