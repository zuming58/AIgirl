import assert from "node:assert/strict";
import test from "node:test";

import {
  CoreApiError,
  coreApi,
  createEventSocket,
} from "../src/services/coreApi.js";

function jsonResponse(value, init = {}) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

test("serializes setting values with the stable request contract", async () => {
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return jsonResponse({
      key: "privacy.memory_enabled",
      value: false,
    });
  };

  const result = await coreApi.updateSetting(
    "privacy.memory_enabled",
    false,
  );

  assert.equal(captured.url, "/core/v1/settings/privacy.memory_enabled");
  assert.equal(captured.options.method, "PUT");
  assert.equal(
    captured.options.headers.get("content-type"),
    "application/json",
  );
  assert.deepEqual(JSON.parse(captured.options.body), { value: false });
  assert.equal(result.value, false);
});

test("returns null for successful no-content mutations", async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 });
  assert.equal(await coreApi.deletePlan("plan id"), null);
});

test("uses stable memory intelligence endpoint contracts", async () => {
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, method: options.method ?? "GET" });
    if (String(url).includes("conversation-summaries?")) {
      return jsonResponse({ items: [], total: 0 });
    }
    if (options.method === "DELETE") return new Response(null, { status: 204 });
    return jsonResponse({ status: "building", pending_count: 2 });
  };

  await coreApi.memoryIndexStatus();
  await coreApi.rebuildMemoryIndex();
  await coreApi.conversationSummaries("session 1");
  await coreApi.generateConversationSummary("session 1");
  await coreApi.deleteConversationSummary("summary 1");

  assert.deepEqual(requests, [
    { url: "/core/v1/memories/index/status", method: "GET" },
    { url: "/core/v1/memories/index/rebuild", method: "POST" },
    {
      url: "/core/v1/conversation-summaries?limit=50&offset=0&session_id=session+1",
      method: "GET",
    },
    { url: "/core/v1/conversations/session%201/summaries", method: "POST" },
    { url: "/core/v1/conversation-summaries/summary%201", method: "DELETE" },
  ]);
});

test("uses privacy-safe music library endpoint contracts", async () => {
  const requests = [];
  globalThis.window = { location: { origin: "http://127.0.0.1:4173" } };
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, method: options.method ?? "GET" });
    return jsonResponse({ status: { status: "ready" }, tracks: [] });
  };

  await coreApi.musicLibrary();
  await coreApi.scanMusicLibrary();

  assert.deepEqual(requests, [
    { url: "/core/v1/music/library", method: "GET" },
    { url: "/core/v1/music/library/scan", method: "POST" },
  ]);
  assert.equal(
    coreApi.musicTrackUrl("track id"),
    "http://127.0.0.1:4173/core/v1/music/tracks/track%20id/audio",
  );
});

test("uses disabled-by-default weather and calendar contracts", async () => {
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push(url);
    return jsonResponse({ status: { status: "disabled" }, events: [] });
  };

  await coreApi.integrationStatuses();
  await coreApi.currentWeather();
  await coreApi.calendarEvents(
    "2026-08-04T00:00:00Z",
    "2026-08-05T00:00:00Z",
  );

  assert.deepEqual(requests, [
    "/core/v1/integrations/status",
    "/core/v1/weather/current",
    "/core/v1/calendar/events?start=2026-08-04T00%3A00%3A00Z&end=2026-08-05T00%3A00%3A00Z",
  ]);
});

test("requests the privacy-safe diagnostics endpoint", async () => {
  let capturedUrl;
  globalThis.fetch = async (url) => {
    capturedUrl = url;
    return jsonResponse({ privacy: { contains_private_content: false } });
  };
  const result = await coreApi.diagnostics();
  assert.equal(capturedUrl, "/core/v1/diagnostics");
  assert.equal(result.privacy.contains_private_content, false);
});

test("adds an explicit confirmation to data imports", async () => {
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return jsonResponse({ imported_rows: 0 });
  };

  await coreApi.importData({ schema_version: 1, data: {} });

  assert.equal(captured.url, "/core/v1/data/import");
  assert.equal(captured.options.method, "POST");
  assert.deepEqual(JSON.parse(captured.options.body), {
    schema_version: 1,
    data: {},
    confirmed: true,
  });
});

test("persists voice transcripts with the realtime event identity", async () => {
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return jsonResponse({ id: "message-1" });
  };

  await coreApi.persistVoiceTranscript({
    session_id: "voice-session",
    transcript_id: "user:item-1",
    role: "user",
    content: "今晚想散步",
  });

  assert.equal(captured.url, "/core/v1/voice/transcripts");
  assert.equal(captured.options.method, "POST");
  assert.deepEqual(JSON.parse(captured.options.body), {
    session_id: "voice-session",
    transcript_id: "user:item-1",
    role: "user",
    content: "今晚想散步",
  });
});

test("builds a same-origin avatar media URL", () => {
  globalThis.window = {
    location: { origin: "http://127.0.0.1:4173" },
  };
  assert.equal(
    coreApi.avatarAssetUrl("thinking"),
    "http://127.0.0.1:4173/core/v1/avatar/assets/thinking",
  );
});

test("preserves structured API error details", async () => {
  globalThis.fetch = async () =>
    jsonResponse(
      { detail: "Plan not found" },
      { status: 404, statusText: "Not Found" },
    );

  await assert.rejects(
    () => coreApi.deletePlan("missing"),
    (error) => {
      assert.ok(error instanceof CoreApiError);
      assert.equal(error.status, 404);
      assert.equal(error.message, "Plan not found");
      assert.deepEqual(error.details, { detail: "Plan not found" });
      return true;
    },
  );
});

test("converts network failures into a local-service error", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("connection refused");
  };

  await assert.rejects(
    () => coreApi.health(),
    (error) => {
      assert.ok(error instanceof CoreApiError);
      assert.equal(error.status, 0);
      assert.equal(error.message, "无法连接本地核心服务");
      return true;
    },
  );
});

test("event socket parses events and closes without reconnecting", () => {
  const received = [];
  const statuses = [];

  class MockWebSocket {
    constructor(url) {
      this.url = String(url);
      this.listeners = new Map();
      MockWebSocket.instance = this;
    }

    addEventListener(name, listener) {
      this.listeners.set(name, listener);
    }

    emit(name, value = {}) {
      this.listeners.get(name)?.(value);
    }

    close() {
      this.closed = true;
      this.emit("close");
    }
  }

  globalThis.window = {
    location: { origin: "http://127.0.0.1:4173" },
    setTimeout,
    clearTimeout,
  };
  globalThis.WebSocket = MockWebSocket;

  const close = createEventSocket(
    (event) => received.push(event),
    (status) => statuses.push(status),
  );
  MockWebSocket.instance.emit("open");
  MockWebSocket.instance.emit("message", {
    data: JSON.stringify({ type: "runtime.ready" }),
  });
  close();

  assert.equal(
    MockWebSocket.instance.url,
    "ws://127.0.0.1:4173/core/v1/app/events",
  );
  assert.deepEqual(received, [{ type: "runtime.ready" }]);
  assert.deepEqual(statuses, ["connected"]);
  assert.equal(MockWebSocket.instance.closed, true);
});
