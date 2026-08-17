# Xinyu Core

`services/core` is the local business service for Xinyu. It owns conversations,
memory, plans, persona versions, mood, runtime state, event envelopes, data
export, and model-provider routing. It does not own microphone capture or avatar
rendering.

The service listens on loopback only by default.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "services\core[dev]"
.\.venv\Scripts\xinyu-core.exe --port 8765
```

Environment variables:

- `XINYU_DATA_DIR`: application data directory.
- `XINYU_AUTH_TOKEN`: optional local API bearer token. Production sidecars must set it.
- `XINYU_LLM_BASE_URL`: optional OpenAI-compatible server, for example `http://127.0.0.1:8080/v1`.
- `XINYU_LLM_MODEL`: model id sent to the compatible server.
- `XINYU_LLM_API_KEY`: optional compatible-server token.
- `XINYU_EMBEDDING_BASE_URL`: optional OpenAI-compatible `/v1` server.
- `XINYU_EMBEDDING_MODEL`: embedding model id; defaults to `BAAI/bge-small-zh-v1.5`.
- `XINYU_EMBEDDING_API_KEY`: optional embedding-server token.

Without a configured LLM server, the API uses a clearly identified deterministic
development provider so the entire persistence and UI path remains testable.
That provider is never used to fabricate conversation summaries. Without a real
LLM, summaries persist an honest `unavailable` state. Without an embedding
server, memory queries continue through FTS5/LIKE. Vector data is derived and is
not included in JSON exports.
