const runtimeEnv = import.meta.env ?? {};
const configuredBase = runtimeEnv.VITE_XINYU_CORE_URL?.replace(/\/$/, "");
const API_BASE = configuredBase || "/core";
const AUTH_TOKEN = runtimeEnv.VITE_XINYU_AUTH_TOKEN || "";

export class CoreApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = "CoreApiError";
    this.status = status;
    this.details = details;
  }
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (AUTH_TOKEN) headers.set("Authorization", `Bearer ${AUTH_TOKEN}`);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (error) {
    throw new CoreApiError("无法连接本地核心服务", 0, error);
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    throw new CoreApiError(
      payload?.detail || `本地服务请求失败（${response.status}）`,
      response.status,
      payload,
    );
  }
  return payload;
}

function jsonOptions(method, value) {
  return {
    method,
    body: value === undefined ? undefined : JSON.stringify(value),
  };
}

function mediaUrl(path) {
  const base =
    API_BASE.startsWith("http://") || API_BASE.startsWith("https://")
      ? API_BASE
      : `${window.location.origin}${API_BASE}`;
  const url = new URL(`${base}${path}`);
  if (AUTH_TOKEN) url.searchParams.set("token", AUTH_TOKEN);
  return url.toString();
}

export const coreApi = {
  health: () => request("/health"),
  runtimeStatus: () => request("/v1/runtime/status"),
  systemCapabilities: () => request("/v1/system/capabilities"),
  diagnostics: () => request("/v1/diagnostics"),
  avatarStatus: () => request("/v1/avatar/status"),
  avatarAssetUrl: (state) =>
    mediaUrl(`/v1/avatar/assets/${encodeURIComponent(state)}`),
  updateAvatarState: (value) =>
    request("/v1/avatar/state", jsonOptions("POST", value)),
  models: () => request("/v1/models"),
  musicLibrary: () => request("/v1/music/library"),
  scanMusicLibrary: () =>
    request("/v1/music/library/scan", { method: "POST" }),
  musicTrackUrl: (id) =>
    mediaUrl(`/v1/music/tracks/${encodeURIComponent(id)}/audio`),
  chat: (value) => request("/v1/chat", jsonOptions("POST", value)),
  conversations: (limit = 50) =>
    request(`/v1/conversations?limit=${limit}`),
  messages: (sessionId) =>
    request(`/v1/conversations/${encodeURIComponent(sessionId)}/messages`),
  queryMemories: (value = {}) =>
    request("/v1/memories/query", jsonOptions("POST", value)),
  memoryIndexStatus: () => request("/v1/memories/index/status"),
  rebuildMemoryIndex: () =>
    request("/v1/memories/index/rebuild", { method: "POST" }),
  createMemory: (value) =>
    request("/v1/memories", jsonOptions("POST", value)),
  memoryContext: (id) =>
    request(`/v1/memories/${encodeURIComponent(id)}/context`),
  updateMemory: (id, value) =>
    request(
      `/v1/memories/${encodeURIComponent(id)}`,
      jsonOptions("PATCH", value),
    ),
  deleteMemory: (id) =>
    request(`/v1/memories/${encodeURIComponent(id)}`, { method: "DELETE" }),
  conversationSummaries: (sessionId = null, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (sessionId) params.set("session_id", sessionId);
    return request(`/v1/conversation-summaries?${params}`);
  },
  generateConversationSummary: (sessionId) =>
    request(
      `/v1/conversations/${encodeURIComponent(sessionId)}/summaries`,
      { method: "POST" },
    ),
  deleteConversationSummary: (id) =>
    request(`/v1/conversation-summaries/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  listPlans: (includeCompleted = true) =>
    request(`/v1/plans?include_completed=${includeCompleted}`),
  createPlan: (value) =>
    request("/v1/plans", jsonOptions("POST", value)),
  updatePlan: (id, value) =>
    request(`/v1/plans/${encodeURIComponent(id)}`, jsonOptions("PATCH", value)),
  deletePlan: (id) =>
    request(`/v1/plans/${encodeURIComponent(id)}`, { method: "DELETE" }),
  notifications: (includeAcknowledged = false) =>
    request(
      `/v1/notifications?include_acknowledged=${includeAcknowledged}&limit=50`,
    ),
  acknowledgeNotification: (id) =>
    request(
      `/v1/notifications/${encodeURIComponent(id)}/acknowledge`,
      { method: "POST" },
    ),
  persona: () => request("/v1/persona"),
  updatePersona: (value) =>
    request("/v1/persona", jsonOptions("PUT", value)),
  mood: () => request("/v1/mood/current"),
  updateMood: (value) => request("/v1/mood", jsonOptions("POST", value)),
  settings: () => request("/v1/settings"),
  updateSetting: (key, value) =>
    request(
      `/v1/settings/${encodeURIComponent(key)}`,
      jsonOptions("PUT", { value }),
    ),
  startVoiceSession: () =>
    request("/v1/voice/session", { method: "POST" }),
  persistVoiceTranscript: (value) =>
    request("/v1/voice/transcripts", jsonOptions("POST", value)),
  exportData: () => request("/v1/data/export"),
  listBackups: () => request("/v1/data/backups"),
  createBackup: () => request("/v1/data/backups", { method: "POST" }),
  importData: (value) =>
    request(
      "/v1/data/import",
      jsonOptions("POST", { ...value, confirmed: true }),
    ),
  restoreBackup: (name) =>
    request(
      `/v1/data/backups/${encodeURIComponent(name)}/restore`,
      jsonOptions("POST", { confirmed: true }),
    ),
  deleteData: () => request("/v1/data", { method: "DELETE" }),
};

export function createEventSocket(onEvent, onStatus = () => {}) {
  const base =
    API_BASE.startsWith("http://") || API_BASE.startsWith("https://")
      ? API_BASE
      : `${window.location.origin}${API_BASE}`;
  const url = new URL(`${base}/v1/app/events`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  if (AUTH_TOKEN) url.searchParams.set("token", AUTH_TOKEN);
  let socket;
  let disposed = false;
  let reconnectTimer;
  let reconnectAttempt = 0;

  function connect() {
    if (disposed) return;
    socket = new WebSocket(url);
    socket.addEventListener("open", () => {
      reconnectAttempt = 0;
      onStatus("connected");
    });
    socket.addEventListener("close", () => {
      if (disposed) return;
      onStatus("disconnected");
      const delay = Math.min(10_000, 500 * 2 ** reconnectAttempt);
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(connect, delay);
    });
    socket.addEventListener("error", () => onStatus("error"));
    socket.addEventListener("message", (event) => {
      try {
        onEvent(JSON.parse(event.data));
      } catch {
        onStatus("error");
      }
    });
  }

  connect();
  return () => {
    disposed = true;
    window.clearTimeout(reconnectTimer);
    socket?.close();
  };
}
