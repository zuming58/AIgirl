import { S2sWsRealtimeClient } from "../../../../third_party/speech-to-speech/demo/ws/s2s-ws-client.js";

const runtimeEnv = import.meta.env ?? {};

function voiceSocketUrl() {
  const configured = runtimeEnv.VITE_XINYU_CORE_URL?.replace(/\/$/, "");
  const token = runtimeEnv.VITE_XINYU_AUTH_TOKEN || "";
  let url;
  if (configured) {
    url = new URL(`${configured}/v1/realtime/voice`);
  } else {
    url = new URL("/core/v1/realtime/voice", window.location.origin);
  }
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  if (token) url.searchParams.set("token", token);
  return url.toString();
}

export async function listMicrophoneDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((device) => device.kind === "audioinput")
    .map((device, index) => ({
      id: device.deviceId,
      label: device.label || `麦克风 ${index + 1}`,
    }));
}

export function createSpeechClient({
  deviceId = "",
  personaName = "心屿",
  onStatus = () => {},
  onTranscript = () => {},
  onResponseFinished = () => {},
  onInputLevel = () => {},
  onError = () => {},
} = {}) {
  let microphoneStream = null;
  const constraints = {
    audio: {
      deviceId: deviceId ? { exact: deviceId } : undefined,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
    video: false,
  };
  const client = new S2sWsRealtimeClient({
    directUrl: voiceSocketUrl(),
    voice: "alloy",
    instructions: `你是${personaName}，请用温暖、简洁、尊重边界的中文陪伴用户。`,
    acquireMic: async () => {
      microphoneStream = await navigator.mediaDevices.getUserMedia(constraints);
      return microphoneStream;
    },
    noiseGate: { enabled: true, thresholdDb: -48 },
  });

  client.addEventListener("status", (event) => {
    onStatus(event.detail?.status ?? "error");
  });
  client.addEventListener("transcript", (event) => {
    onTranscript(event.detail);
  });
  client.addEventListener("response-finished", (event) => {
    onResponseFinished(event.detail);
  });
  client.addEventListener("input-level", (event) => {
    onInputLevel(event.detail?.rms ?? 0);
  });
  client.addEventListener("error", (event) => {
    onError(event.detail?.error ?? new Error("语音连接中断"));
  });
  client.addEventListener("server-error", (event) => {
    onError(event.detail?.error ?? new Error("语音运行时返回错误"));
  });
  const upstreamClose = client.close.bind(client);
  client.close = async () => {
    try {
      await upstreamClose();
    } finally {
      microphoneStream?.getTracks().forEach((track) => track.stop());
      microphoneStream = null;
    }
  };
  return client;
}
