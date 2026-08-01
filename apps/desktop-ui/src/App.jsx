import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowClockwise,
  Bell,
  BookOpen,
  Brain,
  Briefcase,
  Camera,
  CaretRight,
  Check,
  CheckCircle,
  ClockCounterClockwise,
  CloudRain,
  Coffee,
  Compass,
  Cpu,
  Flag,
  Heart,
  LockKey,
  MagnifyingGlass,
  Microphone,
  Minus,
  MoonStars,
  Pause,
  PencilSimple,
  Play,
  Plus,
  SealCheck,
  SkipBack,
  SkipForward,
  Sparkle,
  SpeakerHigh,
  Square,
  Star,
  Target,
  Trash,
  UserCircle,
  Waveform,
  X,
} from "@phosphor-icons/react";
import {
  formatCalendarDate,
  formatConversationTime,
  formatClock,
  formatShortDate,
  memoryIndexStatusLabels,
  profileLabels,
  toMessageView,
  toMemoryView,
  toPlanView,
} from "./domain/viewModels.js";
import { coreApi, createEventSocket } from "./services/coreApi.js";
import { memoryWorkspace } from "./services/memoryWorkspace.js";
import {
  desktopBridge,
  isDesktopRuntime,
} from "./services/desktopBridge.js";
import {
  createSpeechClient,
  listMicrophoneDevices,
} from "./services/speechClient.js";

const navItems = ["此刻", "对话", "回忆", "计划", "更多"];
const defaultNote =
  "一天又要结束了呢，辛苦啦，早点休息哦，我会在这里陪着你的～";
const defaultSettings = {
  "privacy.memory_enabled": true,
  "privacy.proactive_enabled": true,
  "proactive.checkin_enabled": true,
  "avatar.quality": "high",
  "voice.input_device_id": "",
};
const defaultPersona = {
  name: "心屿",
  relationship_role: "companion",
  background: "温暖、尊重边界、记得共同经历的本地陪伴式智能体。",
  voice: {},
  behavior: {},
  boundaries: {},
};

const moods = [
  { label: "安心", hint: "此刻很放松" },
  { label: "甜蜜", hint: "想离你近一点" },
  { label: "想念", hint: "正在等你回来" },
];

const avatarStateLabels = {
  idle: "安静陪伴",
  listening: "正在聆听",
  thinking: "正在想一想",
  speaking: "正在回应",
  smiling: "在对你微笑",
  goodnight: "晚安模式",
};
const voiceStatusLabels = {
  idle: "语音待命",
  "creating-session": "正在建立语音会话",
  queued: "正在等待语音资源",
  "your-turn": "语音资源已就绪",
  connecting: "正在连接语音",
  connected: "正在聆听",
  "user-speaking": "正在聆听你说话",
  processing: "正在想一想",
  "ai-speaking": "心屿正在回应",
  closed: "语音已停止",
  error: "语音连接异常",
};

const initialConversation = [
  {
    id: 1,
    role: "agent",
    text: "你回来啦。今晚想聊聊什么？我会把你明确希望我记住的事情，安静地留在本机。",
    time: "20:26",
  },
];

const initialMemories = [
  {
    id: 1,
    kind: "点滴",
    icon: Camera,
    title: "一起看电影的夜晚",
    summary: "你说比起电影本身，更喜欢有人一起吐槽剧情。",
    date: "2026.07.18",
    source: "对话 18 分钟 · 已确认",
    accent: "rose",
    starred: true,
  },
  {
    id: 2,
    kind: "偏好",
    icon: Coffee,
    title: "咖啡要少糖",
    summary: "工作日下午更喜欢拿铁，晚上不喝咖啡，怕影响睡眠。",
    date: "2026.07.12",
    source: "3 次对话归纳 · 高可信",
    accent: "amber",
    starred: false,
  },
  {
    id: 3,
    kind: "在意",
    icon: Brain,
    title: "项目变更会让你焦虑",
    summary: "临时改需求时，你更需要先被理解，再一起拆解下一步。",
    date: "2026.07.24",
    source: "对话 9 分钟 · 待你确认",
    accent: "violet",
    starred: false,
  },
  {
    id: 4,
    kind: "约定",
    icon: Flag,
    title: "周五晚上留给自己",
    summary: "不加班的话，我们一起选一部电影，吃点喜欢的东西。",
    date: "2026.07.25",
    source: "你主动告诉我 · 已确认",
    accent: "blue",
    starred: true,
  },
];

const initialPlans = [
  {
    id: 1,
    title: "上午 10:00 项目会议",
    meta: "工作 · 会议前 15 分钟提醒",
    time: "10:00",
    group: "工作",
    done: false,
  },
  {
    id: 2,
    title: "午休后走一走",
    meta: "健康 · 目标 20 分钟",
    time: "13:20",
    group: "生活",
    done: false,
  },
  {
    id: 3,
    title: "拿快递",
    meta: "生活 · 回家路上",
    time: "18:30",
    group: "生活",
    done: false,
  },
  {
    id: 4,
    title: "一起看一部电影",
    meta: "我们的约定 · 我来提醒你",
    time: "21:00",
    group: "约定",
    done: false,
  },
];

const tabModes = {
  此刻: "moment",
  对话: "dialogue",
  回忆: "memory",
  计划: "plan",
  更多: "more",
};

function AppIconButton({
  label,
  className = "",
  children,
  onClick,
  pressed,
  title,
  ...buttonProps
}) {
  return (
    <button
      type="button"
      className={`icon-button ${className}`}
      aria-label={label}
      aria-pressed={pressed}
      title={title ?? label}
      onClick={onClick}
      {...buttonProps}
    >
      {children}
    </button>
  );
}

function toLocalDateTimeInput(value) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function App() {
  const [activeTab, setActiveTab] = useState("此刻");
  const [now, setNow] = useState(() => new Date());
  const [coreStatus, setCoreStatus] = useState("connecting");
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [systemCapabilities, setSystemCapabilities] = useState(null);
  const [avatarStatus, setAvatarStatus] = useState(null);
  const [avatarVideoReady, setAvatarVideoReady] = useState(false);
  const [persona, setPersona] = useState(defaultPersona);
  const [personaDraft, setPersonaDraft] = useState(defaultPersona);
  const [settings, setSettings] = useState(defaultSettings);
  const [settingsMessage, setSettingsMessage] = useState("");
  const [latestBackup, setLatestBackup] = useState(null);
  const [autostartEnabled, setAutostartEnabled] = useState(false);
  const [confirmingDataDelete, setConfirmingDataDelete] = useState(false);
  const [confirmingRestore, setConfirmingRestore] = useState(false);
  const [pendingImport, setPendingImport] = useState(null);
  const [sessionId, setSessionId] = useState(() =>
    window.localStorage.getItem("xinyu.session_id"),
  );
  const [isSending, setIsSending] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [trackName, setTrackName] = useState("选择本机音乐");
  const [trackArtist, setTrackArtist] = useState("音乐只在本机播放");
  const [trackUrl, setTrackUrl] = useState("");
  const [playlist, setPlaylist] = useState([]);
  const [currentTrackIndex, setCurrentTrackIndex] = useState(-1);
  const [isListening, setIsListening] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("idle");
  const [microphoneDevices, setMicrophoneDevices] = useState([]);
  const [selectedMicrophone, setSelectedMicrophone] = useState("");
  const [microphoneLevel, setMicrophoneLevel] = useState(0);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [lastMessage, setLastMessage] = useState("");
  const [lastMessageSource, setLastMessageSource] = useState("你说");
  const [conversation, setConversation] = useState(initialConversation);
  const [conversationList, setConversationList] = useState([]);
  const [isConversationHistoryOpen, setIsConversationHistoryOpen] =
    useState(false);
  const [isConversationLoading, setIsConversationLoading] = useState(false);
  const [memories, setMemories] = useState(initialMemories);
  const [memoryMode, setMemoryMode] = useState("memories");
  const [conversationSummaries, setConversationSummaries] = useState([]);
  const [memoryIndex, setMemoryIndex] = useState(null);
  const [memoryWorkspaceBusy, setMemoryWorkspaceBusy] = useState(false);
  const [memoryWorkspaceMessage, setMemoryWorkspaceMessage] = useState("");
  const [memoryFilter, setMemoryFilter] = useState("全部");
  const [memoryQuery, setMemoryQuery] = useState("");
  const [selectedMemoryId, setSelectedMemoryId] = useState(1);
  const [editingMemoryId, setEditingMemoryId] = useState(0);
  const [memoryDraft, setMemoryDraft] = useState({ title: "", summary: "" });
  const [memoryContext, setMemoryContext] = useState(null);
  const [isAddingMemory, setIsAddingMemory] = useState(false);
  const [newMemory, setNewMemory] = useState({
    kind: "preference",
    title: "",
    summary: "",
  });
  const [planItems, setPlanItems] = useState(initialPlans);
  const [notifications, setNotifications] = useState([]);
  const [planFilter, setPlanFilter] = useState("全部");
  const [isAddingPlan, setIsAddingPlan] = useState(false);
  const [editingPlanId, setEditingPlanId] = useState(null);
  const [newPlan, setNewPlan] = useState({
    title: "",
    category: "life",
    dueAt: "",
    remind: true,
  });
  const [moodIndex, setMoodIndex] = useState(0);
  const [note, setNote] = useState(defaultNote);
  const [draftNote, setDraftNote] = useState(note);
  const audioRef = useRef(null);
  const speechClientRef = useRef(null);
  const voiceSessionRef = useRef(null);
  const persistedTranscriptIdsRef = useRef(new Set());
  const musicInputRef = useRef(null);
  const importInputRef = useRef(null);

  const currentMood = moods[moodIndex];
  const tomorrow = useMemo(() => {
    const value = new Date(now);
    value.setDate(value.getDate() + 1);
    return value;
  }, [now]);
  const remainingTasks = useMemo(
    () => planItems.filter((task) => !task.done).length,
    [planItems],
  );
  const tomorrowTasks = useMemo(
    () => planItems.filter((task) => !task.done).slice(0, 3),
    [planItems],
  );
  const filteredMemories = useMemo(
    () => {
      const normalizedQuery = memoryQuery.trim().toLowerCase();
      return memories.filter((memory) => {
        const matchesKind =
          memoryFilter === "全部" || memory.kind === memoryFilter;
        const matchesQuery =
          !normalizedQuery ||
          `${memory.title}${memory.summary}${memory.kind}`
            .toLowerCase()
            .includes(normalizedQuery);
        return matchesKind && matchesQuery;
      });
    },
    [memories, memoryFilter, memoryQuery],
  );
  const selectedMemory =
    memories.find((memory) => memory.id === selectedMemoryId) ?? memories[0];
  const filteredPlans = useMemo(
    () =>
      planFilter === "全部"
        ? planItems
        : planItems.filter((item) => item.group === planFilter),
    [planItems, planFilter],
  );
  const completedPlans = planItems.filter((item) => item.done).length;
  const workPlanCount = planItems.filter(
    (item) => item.category === "work" && !item.done,
  ).length;
  const promisePlanCount = planItems.filter(
    (item) => item.category === "promise" && !item.done,
  ).length;
  const hasSuggestedWalk = planItems.some(
    (item) => item.title === "午休后散步 20 分钟",
  );

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function hydrateFromCore() {
      const results = await Promise.allSettled([
        coreApi.health(),
        coreApi.runtimeStatus(),
        coreApi.systemCapabilities(),
        coreApi.avatarStatus(),
        coreApi.persona(),
        coreApi.queryMemories({ limit: 100 }),
        coreApi.listPlans(true),
        coreApi.settings(),
        coreApi.conversations(),
        coreApi.listBackups(),
        sessionId ? coreApi.messages(sessionId) : Promise.resolve([]),
        coreApi.notifications(),
        memoryWorkspace.load(),
      ]);
      if (cancelled) return;
      const valueAt = (index) =>
        results[index].status === "fulfilled" ? results[index].value : null;
      const health = valueAt(0);
      if (!health) {
        setCoreStatus("offline");
        return;
      }
      setCoreStatus(health.status === "ok" ? "connected" : "degraded");

      const runtime = valueAt(1);
      const capabilities = valueAt(2);
      const avatar = valueAt(3);
      const storedPersona = valueAt(4);
      const storedMemories = valueAt(5);
      const storedPlans = valueAt(6);
      const storedSettings = valueAt(7);
      const storedConversations = valueAt(8);
      const storedBackups = valueAt(9);
      const storedMessages = valueAt(10);
      const storedNotifications = valueAt(11);
      const storedMemoryWorkspace = valueAt(12);

      if (runtime) setRuntimeStatus(runtime);
      if (capabilities) setSystemCapabilities(capabilities);
      if (avatar) setAvatarStatus(avatar);
      if (storedPersona) {
        setPersona(storedPersona);
        setPersonaDraft(storedPersona);
      }
      if (storedSettings) {
        setSettings((current) => ({ ...current, ...storedSettings }));
        if (typeof storedSettings["voice.input_device_id"] === "string") {
          setSelectedMicrophone(storedSettings["voice.input_device_id"]);
        }
      }
      if (storedMemories) {
        const memoryViews = storedMemories.map(toMemoryView);
        setMemories(memoryViews);
        setSelectedMemoryId(memoryViews[0]?.id ?? 0);
      }
      if (storedPlans) {
        setPlanItems(storedPlans.map(toPlanView));
      }
      if (storedConversations) {
        setConversationList(storedConversations);
      }
      if (storedBackups) {
        setLatestBackup(storedBackups[0] ?? null);
      }
      if (storedNotifications) {
        setNotifications(storedNotifications);
      }
      if (storedMemoryWorkspace) {
        setMemoryIndex(storedMemoryWorkspace.index);
        setConversationSummaries(storedMemoryWorkspace.summaries);
      }
      if (sessionId && storedMessages) {
        setConversation(storedMessages.map(toMessageView));
      }
      if (typeof storedSettings?.["companion.evening_note"] === "string") {
        setNote(storedSettings["companion.evening_note"]);
        setDraftNote(storedSettings["companion.evening_note"]);
      }
    }
    hydrateFromCore();
    const closeEvents = createEventSocket(
      (event) => {
        if (event.type === "runtime.degraded") setCoreStatus("degraded");
        if (event.type === "runtime.ready") setCoreStatus("connected");
        if (event.type === "avatar.state.changed") {
          setAvatarStatus(event.payload);
        }
        if (event.type === "plan.reminder_due") {
          const task = event.payload?.task;
          const notificationId = event.payload?.notification_id;
          if (notificationId) {
            setNotifications((items) => [
              {
                id: notificationId,
                event_type: event.type,
                payload: { task },
                status: "delivered",
                delivered_at: new Date().toISOString(),
              },
              ...items.filter((item) => item.id !== notificationId),
            ]);
          }
          setLastMessage(
            task?.title
              ? task.title
              : "有一条计划到提醒时间了。",
          );
          setLastMessageSource("提醒");
          if (task?.title) {
            desktopBridge.notify("心屿 · 计划提醒", task.title).catch(() => {});
          }
        }
        if (event.type === "companion.checkin_due") {
          const notificationId = event.payload?.notification_id;
          const checkinMessage = event.payload?.message;
          if (notificationId) {
            setNotifications((items) => [
              {
                id: notificationId,
                event_type: event.type,
                reason: event.payload?.reason,
                payload: {
                  message: checkinMessage,
                  kind: event.payload?.kind,
                },
                status: "delivered",
                delivered_at: new Date().toISOString(),
              },
              ...items.filter((item) => item.id !== notificationId),
            ]);
          }
          if (checkinMessage) {
            setLastMessage(checkinMessage);
            setLastMessageSource(persona.name);
            desktopBridge
              .notify(`${persona.name} · 想起你了`, checkinMessage)
              .catch(() => {});
          }
        }
        if (event.type === "notification.acknowledged") {
          setNotifications((items) =>
            items.filter((item) => item.id !== event.payload?.id),
          );
        }
        if (event.type === "memory.committed") {
          coreApi
            .queryMemories({ limit: 100 })
            .then((items) => setMemories(items.map(toMemoryView)))
            .catch(() => {});
        }
      },
      (status) => {
        if (status === "connected") {
          setCoreStatus("connected");
          hydrateFromCore();
        }
        if (status === "disconnected" || status === "error") {
          setCoreStatus("offline");
        }
      },
    );
    return () => {
      cancelled = true;
      closeEvents();
    };
  }, [sessionId, persona.name]);

  useEffect(() => {
    let cancelled = false;
    setMemoryContext(null);
    if (coreStatus !== "connected" || typeof selectedMemoryId !== "string") {
      return () => {
        cancelled = true;
      };
    }
    coreApi
      .memoryContext(selectedMemoryId)
      .then((context) => {
        if (!cancelled) setMemoryContext(context);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [coreStatus, selectedMemoryId]);

  useEffect(() => {
    desktopBridge
      .isAutostartEnabled()
      .then(setAutostartEnabled)
      .catch(() => setAutostartEnabled(false));
  }, []);

  useEffect(() => {
    let cancelled = false;
    listMicrophoneDevices()
      .then((devices) => {
        if (!cancelled) setMicrophoneDevices(devices);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(
    () => () => {
      const client = speechClientRef.current;
      speechClientRef.current = null;
      client?.close().catch(() => {});
    },
    [],
  );

  useEffect(() => {
    if (!trackUrl || !audioRef.current) return undefined;
    const audio = audioRef.current;
    audio.src = trackUrl;
    audio.load();
    audio.play().catch(() => setIsPlaying(false));
    return undefined;
  }, [trackUrl]);

  useEffect(() => {
    setAvatarVideoReady(false);
  }, [avatarStatus?.state, avatarStatus?.renderer]);

  useEffect(
    () => () => {
      playlist.forEach((track) => URL.revokeObjectURL(track.url));
    },
    [playlist],
  );

  async function sendMessage(event) {
    event.preventDefault();
    const cleanMessage = message.trim();
    if (!cleanMessage || isSending) return;
    const now = new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date());
    const optimisticId = Date.now();
    setConversation((items) => [
      ...items,
      { id: optimisticId, role: "user", text: cleanMessage, time: now },
    ]);
    setLastMessage(cleanMessage);
    setLastMessageSource("你说");
    if (activeTab !== "对话") setActiveTab("对话");
    setMessage("");
    setIsListening(false);
    setIsSending(true);
    try {
      const response = await coreApi.chat({
        message: cleanMessage,
        session_id: sessionId,
        channel: "text",
      });
      setSessionId(response.session_id);
      window.localStorage.setItem("xinyu.session_id", response.session_id);
      setConversation((items) => [
        ...items,
        {
          id: response.assistant_message.id,
          role: "agent",
          text: response.reply,
          time: now,
          memory: response.memory_candidates.length
            ? "已保存为一条可管理的记忆"
            : undefined,
        },
      ]);
      if (response.memory_candidates.length) {
        const storedMemories = await coreApi.queryMemories({ limit: 100 });
        const memoryViews = storedMemories.map(toMemoryView);
        setMemories(memoryViews);
        setSelectedMemoryId(memoryViews[0]?.id ?? 0);
      }
      setConversationList(await coreApi.conversations());
      setCoreStatus("connected");
    } catch {
      setConversation((items) => [
        ...items,
        {
          id: optimisticId + 1,
          role: "agent",
          text: "本地核心服务暂时没有响应，但你刚才说的话还留在这个页面里。服务恢复后我们再继续。",
          time: now,
        },
      ]);
      setCoreStatus("offline");
    } finally {
      setIsSending(false);
    }
  }

  function changeTab(item) {
    setActiveTab(item);
    if (item !== "更多") setDraftNote(note);
  }

  async function saveNote() {
    const cleanNote = draftNote.trim();
    if (!cleanNote) return;
    if (coreStatus !== "connected") {
      setLastMessage("本地服务离线，晚安心语没有保存。");
      setLastMessageSource("系统");
      return;
    }
    try {
      await coreApi.updateSetting("companion.evening_note", cleanNote);
      setNote(cleanNote);
      setActiveTab("此刻");
    } catch {
      setCoreStatus("offline");
      setLastMessage("保存失败，原来的晚安心语保持不变。");
      setLastMessageSource("系统");
    }
  }

  async function toggleMemoryStar(id) {
    const current = memories.find((item) => item.id === id);
    setMemories((items) =>
      items.map((item) =>
        item.id === id ? { ...item, starred: !item.starred } : item,
      ),
    );
    if (coreStatus === "connected" && typeof id === "string") {
      try {
        await coreApi.updateMemory(id, { starred: !current?.starred });
      } catch {
        setMemories((items) =>
          items.map((item) =>
            item.id === id ? { ...item, starred: current?.starred } : item,
          ),
        );
        setCoreStatus("offline");
      }
    }
  }

  async function forgetMemory(id) {
    if (coreStatus === "connected" && typeof id === "string") {
      try {
        await coreApi.deleteMemory(id);
      } catch {
        setCoreStatus("offline");
        return;
      }
    }
    setMemories((items) => items.filter((item) => item.id !== id));
    const nextMemory = memories.find((item) => item.id !== id);
    setSelectedMemoryId(nextMemory?.id ?? 0);
  }

  function startMemoryEdit(memory) {
    if (editingMemoryId === memory.id) {
      setEditingMemoryId(0);
      return;
    }
    setEditingMemoryId(memory.id);
    setMemoryDraft({ title: memory.title, summary: memory.summary });
  }

  async function saveMemoryEdit(event) {
    event.preventDefault();
    const title = memoryDraft.title.trim();
    const summary = memoryDraft.summary.trim();
    if (!title || !summary) return;
    const previous = memories.find((item) => item.id === editingMemoryId);
    setMemories((items) =>
      items.map((item) =>
        item.id === editingMemoryId ? { ...item, title, summary } : item,
      ),
    );
    setEditingMemoryId(0);
    if (
      coreStatus === "connected" &&
      typeof editingMemoryId === "string"
    ) {
      try {
        await coreApi.updateMemory(editingMemoryId, {
          title,
          content: summary,
          user_confirmed: true,
        });
      } catch {
        if (previous) {
          setMemories((items) =>
            items.map((item) =>
              item.id === previous.id ? previous : item,
            ),
          );
        }
        setCoreStatus("offline");
      }
    }
  }

  async function addMemory(event) {
    event.preventDefault();
    const title = newMemory.title.trim();
    const content = newMemory.summary.trim();
    if (!title || !content) return;
    if (coreStatus !== "connected") {
      setLastMessage("本地服务离线，这条记忆尚未保存。");
      setLastMessageSource("系统");
      return;
    }
    try {
      const stored = await coreApi.createMemory({
        kind: newMemory.kind,
        title,
        content,
        source: "user_explicit",
        confidence: 1,
        salience: 0.8,
        user_confirmed: true,
      });
      const memory = toMemoryView(stored);
      setMemories((items) => [
        memory,
        ...items.filter((item) => item.id !== memory.id),
      ]);
      setSelectedMemoryId(memory.id);
      setNewMemory({ kind: "preference", title: "", summary: "" });
      setIsAddingMemory(false);
    } catch {
      setCoreStatus("offline");
      setLastMessage("记忆保存失败，请在核心服务恢复后再试。");
      setLastMessageSource("系统");
    }
  }

  async function rebuildMemoryIndex() {
    if (coreStatus !== "connected" || memoryWorkspaceBusy) return;
    setMemoryWorkspaceBusy(true);
    setMemoryWorkspaceMessage("");
    try {
      const status = await memoryWorkspace.rebuildIndex();
      setMemoryIndex(status);
      setMemoryWorkspaceMessage("语义索引重建已开始，关键词检索仍可正常使用。");
    } catch {
      setMemoryWorkspaceMessage("索引重建请求失败，当前会继续使用关键词检索。");
    } finally {
      setMemoryWorkspaceBusy(false);
    }
  }

  async function rebuildConversationSummary(summary) {
    if (memoryWorkspaceBusy) return;
    setMemoryWorkspaceBusy(true);
    setMemoryWorkspaceMessage("");
    try {
      const items = await memoryWorkspace.generateSummary(summary.sessionId);
      setConversationSummaries(items);
      setMemoryWorkspaceMessage("摘要生成任务已提交。");
    } catch {
      setMemoryWorkspaceMessage("摘要任务未能提交，请确认本地模型已配置。");
    } finally {
      setMemoryWorkspaceBusy(false);
    }
  }

  async function deleteConversationSummary(id) {
    if (memoryWorkspaceBusy) return;
    setMemoryWorkspaceBusy(true);
    setMemoryWorkspaceMessage("");
    try {
      const items = await memoryWorkspace.deleteSummary(id);
      setConversationSummaries(items);
      setMemoryWorkspaceMessage("摘要已删除，不再用于后续对话。");
    } catch {
      setMemoryWorkspaceMessage("摘要删除失败，当前内容保持不变。");
    } finally {
      setMemoryWorkspaceBusy(false);
    }
  }

  async function generateCurrentSummary() {
    if (!sessionId || memoryWorkspaceBusy) return;
    await rebuildConversationSummary({ sessionId });
  }

  async function togglePlan(id) {
    const current = planItems.find((item) => item.id === id);
    setPlanItems((items) =>
      items.map((item) =>
        item.id === id ? { ...item, done: !item.done } : item,
      ),
    );
    if (coreStatus === "connected" && typeof id === "string") {
      try {
        await coreApi.updatePlan(id, {
          status: current?.done ? "pending" : "completed",
        });
      } catch {
        setPlanItems((items) =>
          items.map((item) =>
            item.id === id ? { ...item, done: current?.done } : item,
          ),
        );
        setCoreStatus("offline");
      }
    }
  }

  async function deletePlan(id) {
    if (coreStatus !== "connected" || typeof id !== "string") {
      setLastMessage("本地服务离线，这条计划没有删除。");
      setLastMessageSource("系统");
      return;
    }
    try {
      await coreApi.deletePlan(id);
      setPlanItems((items) => items.filter((item) => item.id !== id));
      if (editingPlanId === id) {
        setEditingPlanId(null);
        setIsAddingPlan(false);
      }
    } catch {
      setCoreStatus("offline");
      setLastMessage("删除计划失败，请在核心服务恢复后重试。");
      setLastMessageSource("系统");
    }
  }

  async function acknowledgeNotification(id) {
    try {
      await coreApi.acknowledgeNotification(id);
      setNotifications((items) => items.filter((item) => item.id !== id));
    } catch {
      setLastMessage("提醒暂时无法归档，请稍后再试。");
      setLastMessageSource("系统");
    }
  }

  async function addPlan(event) {
    event.preventDefault();
    const cleanTitle = newPlan.title.trim();
    if (!cleanTitle) return;
    if (coreStatus !== "connected") {
      setLastMessage("本地服务离线，这条计划尚未保存。");
      setLastMessageSource("系统");
      return;
    }
    let nextPlan;
    try {
      const dueAt = newPlan.dueAt ? new Date(newPlan.dueAt) : null;
      const reminderAt =
        dueAt && newPlan.remind
          ? new Date(dueAt.getTime() - 15 * 60_000)
          : null;
      const value = {
        title: cleanTitle,
        category: newPlan.category,
        due_at: dueAt?.toISOString() ?? null,
        reminder_at: reminderAt?.toISOString() ?? null,
      };
      const stored =
        typeof editingPlanId === "string"
          ? await coreApi.updatePlan(editingPlanId, value)
          : await coreApi.createPlan({ ...value, source: "user" });
      nextPlan = toPlanView(stored);
    } catch {
      setCoreStatus("offline");
      setLastMessage("计划保存失败，请在核心服务恢复后再试。");
      setLastMessageSource("系统");
      return;
    }
    setPlanItems((items) =>
      typeof editingPlanId === "string"
        ? items.map((item) => (item.id === editingPlanId ? nextPlan : item))
        : [...items, nextPlan],
    );
    setNewPlan({ title: "", category: "life", dueAt: "", remind: true });
    setEditingPlanId(null);
    setIsAddingPlan(false);
  }

  async function acceptPlanSuggestion() {
    if (hasSuggestedWalk) return;
    if (coreStatus !== "connected") {
      setLastMessage("本地服务离线，建议计划没有保存。");
      setLastMessageSource("系统");
      return;
    }
    const dueAt = new Date(tomorrow);
    dueAt.setHours(13, 0, 0, 0);
    try {
      const stored = await coreApi.createPlan({
        title: "午休后散步 20 分钟",
        description: "心屿建议 · 给忙碌日程留一点缓冲",
        category: "life",
        due_at: dueAt.toISOString(),
        source: "assistant",
      });
      setPlanItems((items) => [...items, toPlanView(stored)]);
    } catch {
      setCoreStatus("offline");
      setLastMessage("建议计划保存失败，请在服务恢复后再试。");
      setLastMessageSource("系统");
    }
  }

  function updateAvatarForVoice(status) {
    const stateByStatus = {
      connected: ["listening", "attentive", 0.45],
      "user-speaking": ["listening", "attentive", 0.65],
      processing: ["thinking", "curious", 0.55],
      "ai-speaking": ["speaking", "warm", 0.65],
      closed: ["idle", "calm", 0.35],
      error: ["idle", "calm", 0.35],
    };
    const next = stateByStatus[status];
    if (!next || coreStatus === "offline") return;
    coreApi
      .updateAvatarState({
        state: next[0],
        emotion: next[1],
        intensity: next[2],
      })
      .then(setAvatarStatus)
      .catch(() => {});
  }

  async function persistVoiceTranscript(detail, finalText = detail?.text) {
    const cleanText = finalText?.trim();
    const voiceSession = voiceSessionRef.current;
    if (!cleanText || !voiceSession?.session_id) return;
    const upstreamId = detail?.itemId || detail?.responseId;
    const transcriptId = `${detail.role}:${
      upstreamId || cleanText.slice(0, 180)
    }`;
    if (persistedTranscriptIdsRef.current.has(transcriptId)) return;
    persistedTranscriptIdsRef.current.add(transcriptId);
    try {
      const stored = await coreApi.persistVoiceTranscript({
        session_id: voiceSession.session_id,
        transcript_id: transcriptId,
        role: detail.role,
        content: cleanText,
        metadata: {
          provider: "speech-to-speech",
          upstream_id: upstreamId || null,
          response_status: detail.status || null,
        },
      });
      setConversation((items) =>
        items.some((item) => item.id === stored.id)
          ? items
          : [...items, toMessageView(stored)],
      );
    } catch {
      persistedTranscriptIdsRef.current.delete(transcriptId);
      setLastMessage("语音已经识别，但这条转写暂时没有保存到本机。");
      setLastMessageSource("语音");
    }
  }

  function handleVoiceTranscript(detail) {
    const cleanText = detail?.text?.trim();
    if (!cleanText) return;
    setLastMessage(cleanText);
    setLastMessageSource(detail.role === "assistant" ? persona.name : "你说");
    if (detail.role === "user" && !detail.partial) {
      void persistVoiceTranscript(detail);
    }
  }

  function handleVoiceResponseFinished(detail) {
    const cleanText = detail?.transcript?.trim();
    if (!cleanText) return;
    if (detail.status === "cancelled" && !detail.audible) return;
    void persistVoiceTranscript(
      {
        ...detail,
        role: "assistant",
      },
      cleanText,
    );
  }

  function handleVoiceStatus(status) {
    setVoiceStatus(status);
    setIsListening(!["closed", "error", "idle"].includes(status));
    updateAvatarForVoice(status);
  }

  async function stopVoiceSession() {
    const client = speechClientRef.current;
    speechClientRef.current = null;
    setIsListening(false);
    setVoiceStatus("closed");
    setMicrophoneLevel(0);
    try {
      await client?.close();
    } catch {
      // The local session is already being stopped; cleanup is best effort.
    }
    updateAvatarForVoice("closed");
  }

  async function toggleListening() {
    if (speechClientRef.current || isListening) {
      await stopVoiceSession();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setLastMessage("当前运行环境不支持麦克风输入，文字对话仍然可用。");
      setLastMessageSource("语音");
      return;
    }
    try {
      setVoiceStatus("creating-session");
      const voiceSession = await coreApi.startVoiceSession();
      if (voiceSession.status !== "ready") {
        setLastMessage(voiceSession.detail);
        setLastMessageSource("语音");
        setVoiceStatus("idle");
        setIsListening(false);
        return;
      }

      voiceSessionRef.current = voiceSession;
      persistedTranscriptIdsRef.current = new Set();
      setSessionId(voiceSession.session_id);
      window.localStorage.setItem("xinyu.session_id", voiceSession.session_id);
      setConversation([]);

      const client = createSpeechClient({
        deviceId: selectedMicrophone,
        personaName: persona.name,
        onStatus: handleVoiceStatus,
        onTranscript: handleVoiceTranscript,
        onResponseFinished: handleVoiceResponseFinished,
        onInputLevel: setMicrophoneLevel,
        onError: (error) => {
          const denied =
            error?.name === "NotAllowedError" ||
            error?.name === "SecurityError";
          setLastMessage(
            denied
              ? "没有获得麦克风权限；你可以在系统隐私设置中允许后重试。"
              : "语音连接已中断，文字对话仍然可用。",
          );
          setLastMessageSource("语音");
          void stopVoiceSession();
        },
      });
      speechClientRef.current = client;
      setIsListening(true);
      await client.connect();
    } catch (error) {
      const denied =
        error?.name === "NotAllowedError" || error?.name === "SecurityError";
      await stopVoiceSession();
      setVoiceStatus("error");
      setLastMessage(
        denied
          ? "没有获得麦克风权限；你可以在系统隐私设置中允许后重试。"
          : "语音服务连接失败，文字对话仍然可用。",
      );
      setLastMessageSource("语音");
    }
  }

  async function detectMicrophones() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setSettingsMessage("当前运行环境不支持麦克风输入。");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const devices = await listMicrophoneDevices();
      setMicrophoneDevices(devices);
      setSettingsMessage(
        devices.length
          ? `已检测到 ${devices.length} 个麦克风。`
          : "没有检测到可用麦克风。",
      );
    } catch {
      setSettingsMessage("未获得麦克风权限；没有修改任何系统设置。");
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
    }
  }

  async function selectMicrophone(event) {
    const deviceId = event.target.value;
    setSelectedMicrophone(deviceId);
    setSettings((current) => ({
      ...current,
      "voice.input_device_id": deviceId,
    }));
    try {
      await coreApi.updateSetting("voice.input_device_id", deviceId);
      setSettingsMessage("麦克风选择已保存到本机。");
    } catch {
      setSettingsMessage("麦克风选择暂时无法保存。");
    }
  }

  function chooseMusic() {
    musicInputRef.current?.click();
  }

  function loadMusic(event) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    const nextPlaylist = files.map((file, index) => ({
      id: `${file.name}:${file.size}:${file.lastModified}:${index}`,
      name: file.name.replace(/\.[^.]+$/, ""),
      file,
      url: URL.createObjectURL(file),
    }));
    setPlaylist(nextPlaylist);
    setCurrentTrackIndex(0);
    setTrackName(nextPlaylist[0].name);
    setTrackArtist(`本机歌单 · 1/${nextPlaylist.length}`);
    setProgress(0);
    setTrackUrl(nextPlaylist[0].url);
    event.target.value = "";
  }

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!trackUrl || !audio) {
      chooseMusic();
      return;
    }
    if (audio.paused) {
      try {
        await audio.play();
      } catch {
        setIsPlaying(false);
      }
    } else {
      audio.pause();
    }
  }

  function previousTrack() {
    const audio = audioRef.current;
    if (!audio || !trackUrl) {
      chooseMusic();
      return;
    }
    if (audio.currentTime > 3 || playlist.length < 2) {
      audio.currentTime = 0;
      setProgress(0);
      return;
    }
    const nextIndex =
      (currentTrackIndex - 1 + playlist.length) % playlist.length;
    playTrackAt(nextIndex);
  }

  function nextTrack() {
    if (!playlist.length) {
      chooseMusic();
      return;
    }
    if (playlist.length === 1) {
      const audio = audioRef.current;
      if (audio) {
        audio.currentTime = 0;
        setProgress(0);
      }
      return;
    }
    playTrackAt((currentTrackIndex + 1) % playlist.length);
  }

  function playTrackAt(index) {
    const track = playlist[index];
    if (!track) return;
    setCurrentTrackIndex(index);
    setTrackName(track.name);
    setTrackArtist(`本机歌单 · ${index + 1}/${playlist.length}`);
    setTrackUrl(track.url);
    setProgress(0);
  }

  function handleTrackEnded() {
    if (
      playlist.length > 1 &&
      currentTrackIndex >= 0 &&
      currentTrackIndex < playlist.length - 1
    ) {
      playTrackAt(currentTrackIndex + 1);
      return;
    }
    const audio = audioRef.current;
    if (audio) {
      audio.currentTime = 0;
    }
    setIsPlaying(false);
    setProgress(0);
  }

  function seekTrack(event) {
    const nextProgress = Number(event.target.value);
    const audio = audioRef.current;
    setProgress(nextProgress);
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) {
      audio.currentTime = (nextProgress / 100) * audio.duration;
    }
  }

  function syncTrackProgress() {
    const audio = audioRef.current;
    if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
    setProgress((audio.currentTime / audio.duration) * 100);
  }

  function toggleMute() {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !audio.muted;
    setIsMuted(audio.muted);
  }

  function startNewConversation() {
    window.localStorage.removeItem("xinyu.session_id");
    setSessionId(null);
    setConversation(initialConversation);
    setIsConversationHistoryOpen(false);
    setLastMessage("");
    setMessage("");
  }

  async function openConversation(nextSessionId) {
    if (nextSessionId === sessionId || isConversationLoading) {
      setIsConversationHistoryOpen(false);
      return;
    }
    setIsConversationLoading(true);
    try {
      const storedMessages = await coreApi.messages(nextSessionId);
      setSessionId(nextSessionId);
      window.localStorage.setItem("xinyu.session_id", nextSessionId);
      setConversation(storedMessages.map(toMessageView));
      setIsConversationHistoryOpen(false);
      setCoreStatus("connected");
    } catch {
      setCoreStatus("offline");
      setLastMessage("历史对话读取失败，请在本地服务恢复后重试。");
      setLastMessageSource("系统");
    } finally {
      setIsConversationLoading(false);
    }
  }

  function openPlanForm() {
    if (isAddingPlan) {
      setIsAddingPlan(false);
      setEditingPlanId(null);
      return;
    }
    const defaultDueAt = new Date(tomorrow);
    defaultDueAt.setHours(9, 0, 0, 0);
    setEditingPlanId(null);
    setNewPlan({
      title: "",
      category: "life",
      dueAt: toLocalDateTimeInput(defaultDueAt),
      remind: true,
    });
    setIsAddingPlan(true);
  }

  function startPlanEdit(item) {
    setEditingPlanId(item.id);
    setNewPlan({
      title: item.title,
      category: item.category,
      dueAt: item.dueAt ? toLocalDateTimeInput(item.dueAt) : "",
      remind: Boolean(item.reminderAt),
    });
    setIsAddingPlan(true);
  }

  async function cycleMood() {
    const nextIndex = (moodIndex + 1) % moods.length;
    setMoodIndex(nextIndex);
    if (coreStatus === "connected") {
      const moodValues = [
        { valence: 0.45, arousal: 0.2, energy: 0.5, closeness: 0.7, stress: 0.08 },
        { valence: 0.8, arousal: 0.4, energy: 0.65, closeness: 0.85, stress: 0.04 },
        { valence: 0.2, arousal: 0.35, energy: 0.45, closeness: 0.8, stress: 0.12 },
      ];
      try {
        await coreApi.updateMood({
          ...moodValues[nextIndex],
          reason: "user_adjusted",
        });
      } catch {
        setMoodIndex(moodIndex);
        setCoreStatus("offline");
      }
    }
  }

  async function toggleSetting(key) {
    const nextValue = !settings[key];
    setSettings((current) => ({ ...current, [key]: nextValue }));
    setSettingsMessage("");
    if (coreStatus !== "connected") {
      setSettings((current) => ({ ...current, [key]: settings[key] }));
      setSettingsMessage("本地核心服务离线，设置未更改。");
      return;
    }
    try {
      await coreApi.updateSetting(key, nextValue);
      setSettingsMessage("设置已保存在本机。");
    } catch {
      setSettings((current) => ({ ...current, [key]: settings[key] }));
      setCoreStatus("offline");
      setSettingsMessage("保存失败，本地核心服务已断开。");
    }
  }

  async function toggleAutostart() {
    if (!isDesktopRuntime()) {
      setSettingsMessage("开机启动会在 Tauri 桌面安装版中启用。");
      return;
    }
    const nextValue = !autostartEnabled;
    try {
      await desktopBridge.setAutostart(nextValue);
      setAutostartEnabled(nextValue);
      setSettingsMessage(nextValue ? "已开启开机启动。" : "已关闭开机启动。");
    } catch {
      setSettingsMessage("系统没有完成开机启动设置，请稍后重试。");
    }
  }

  async function savePersona(event) {
    event.preventDefault();
    const name = personaDraft.name.trim();
    const background = personaDraft.background.trim();
    if (!name || !background) return;
    if (coreStatus !== "connected") {
      setSettingsMessage("本地核心服务离线，人格设定未保存。");
      return;
    }
    try {
      const stored = await coreApi.updatePersona({
        name,
        relationship_role: personaDraft.relationship_role || "companion",
        background,
        voice: persona.voice ?? {},
        behavior: persona.behavior ?? {},
        boundaries: persona.boundaries ?? {},
      });
      setPersona(stored);
      setPersonaDraft(stored);
      setSettingsMessage(`已保存 ${stored.name} 的人格版本 v${stored.version}。`);
    } catch {
      setCoreStatus("offline");
      setPersonaDraft(persona);
      setSettingsMessage("人格保存失败，已恢复上一版本。");
    }
  }

  async function exportLocalData() {
    setSettingsMessage("");
    try {
      const payload = await coreApi.exportData();
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `xinyu-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setSettingsMessage("本地数据已导出为 JSON 文件。");
    } catch {
      setCoreStatus("offline");
      setSettingsMessage("导出失败，请确认本地核心服务正在运行。");
    }
  }

  async function exportDiagnostics() {
    setSettingsMessage("");
    try {
      const payload = await coreApi.diagnostics();
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `xinyu-diagnostics-${new Date()
        .toISOString()
        .slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setSettingsMessage("已导出不含对话正文、记忆正文和本地路径的诊断报告。");
    } catch {
      setSettingsMessage("诊断报告导出失败，请确认本地核心服务正在运行。");
    }
  }

  async function createLocalBackup() {
    try {
      const backup = await coreApi.createBackup();
      setLatestBackup(backup);
      setSettingsMessage(`已创建本地快照：${backup.name}`);
    } catch {
      setCoreStatus("offline");
      setSettingsMessage("备份失败，请确认本地核心服务正在运行。");
    }
  }

  async function restoreLatestBackup() {
    if (!latestBackup) return;
    if (!confirmingRestore) {
      setConfirmingDataDelete(false);
      setConfirmingRestore(true);
      setSettingsMessage(
        "恢复会用该快照覆盖当前数据；再次点击“确认恢复”才会执行。",
      );
      return;
    }
    try {
      await coreApi.restoreBackup(latestBackup.name);
      window.localStorage.removeItem("xinyu.session_id");
      setSettingsMessage("恢复完成，正在重新载入本地数据。");
      window.setTimeout(() => window.location.reload(), 250);
    } catch {
      setSettingsMessage("恢复失败，当前数据保持不变。");
      setConfirmingRestore(false);
    }
  }

  async function selectImportFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) {
      setSettingsMessage("导入文件超过 25 MB，请先确认是否选错了文件。");
      return;
    }
    try {
      const payload = JSON.parse(await file.text());
      if (
        !Number.isInteger(payload.schema_version) ||
        !payload.data ||
        typeof payload.data !== "object"
      ) {
        throw new Error("invalid export");
      }
      setPendingImport({ name: file.name, payload });
      setConfirmingRestore(false);
      setConfirmingDataDelete(false);
      setSettingsMessage(
        `已验证文件结构：${file.name}。点击“确认导入”后才会覆盖当前数据。`,
      );
    } catch {
      setPendingImport(null);
      setSettingsMessage("无法读取该文件，它不是有效的心屿 JSON 导出。");
    }
  }

  async function importLocalData() {
    if (!pendingImport) return;
    try {
      await coreApi.importData(pendingImport.payload);
      window.localStorage.removeItem("xinyu.session_id");
      setSettingsMessage("导入完成，正在重新载入本地数据。");
      window.setTimeout(() => window.location.reload(), 250);
    } catch {
      setSettingsMessage(
        "导入没有执行：文件版本或数据约束不兼容，当前数据保持不变。",
      );
    }
  }

  async function deleteLocalData() {
    if (!confirmingDataDelete) {
      setConfirmingRestore(false);
      setConfirmingDataDelete(true);
      setSettingsMessage("再次点击“确认清除”才会删除本地对话、记忆和计划。");
      return;
    }
    try {
      await coreApi.deleteData();
      window.localStorage.removeItem("xinyu.session_id");
      setSessionId(null);
      setConversation([]);
      setMemories([]);
      setPlanItems([]);
      setNotifications([]);
      setSelectedMemoryId(0);
      setSettings(defaultSettings);
      setPersona(defaultPersona);
      setPersonaDraft(defaultPersona);
      setNote(defaultNote);
      setDraftNote(defaultNote);
      setConfirmingDataDelete(false);
      coreApi
        .listBackups()
        .then((backups) => setLatestBackup(backups[0] ?? null))
        .catch(() => {});
      setSettingsMessage("清除前已自动备份；本地用户数据和基础配置已重置。");
    } catch {
      setCoreStatus("offline");
      setSettingsMessage("清除失败，未修改现有本地数据。");
    }
  }

  return (
    <main className={`companion-shell view-${tabModes[activeTab]}`}>
      <img
        className="room-background"
        src="/assets/xinyu-room-hero-reference-layout-v4.png"
        alt="温暖夜晚的房间里，心屿坐在放着日记本的书桌前陪伴用户"
      />
      {avatarStatus?.renderer === "video_state_library" &&
        avatarStatus.available_states?.includes(avatarStatus.state) && (
          <video
            key={avatarStatus.state}
            className={`room-background avatar-state-video ${
              avatarVideoReady ? "ready" : ""
            }`}
            src={coreApi.avatarAssetUrl(avatarStatus.state)}
            autoPlay
            loop
            muted
            playsInline
            preload="auto"
            aria-hidden="true"
            onCanPlay={() => setAvatarVideoReady(true)}
            onError={() => setAvatarVideoReady(false)}
          />
        )}
      <div className="ambient-shade" aria-hidden="true" />

      <header className="topbar">
        <button
          type="button"
          className="brand"
          aria-label="心屿首页"
          onClick={() => changeTab("此刻")}
        >
          <span className="brand-mark">
            <img
              className="brand-crystal"
              src="/assets/xinyu-glass-heart-transparent.png"
              alt=""
              aria-hidden="true"
            />
            <img
              className="brand-pulse"
              src="/assets/xinyu-heartbeat-pulse-transparent.png"
              alt=""
              aria-hidden="true"
            />
          </span>
          <span className="brand-copy">
            <span className="brand-line">
              <strong>心屿</strong>
              <b>XINYU</b>
            </span>
            <small>你的陪伴式桌面智能体</small>
          </span>
        </button>

        <nav className="capsule-nav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              type="button"
              key={item}
              className={activeTab === item ? "active" : ""}
              onClick={() => changeTab(item)}
            >
              {item}
            </button>
          ))}
        </nav>

        <div className="system-strip">
          <div className="clock-block">
            <strong>{formatClock(now)}</strong>
            <span>{formatCalendarDate(now)}</span>
          </div>
          <div className="weather">
            <CloudRain size={25} weight="duotone" />
            <span>
              <strong>--°C</strong>
              <small>天气未连接</small>
            </span>
          </div>
          <span
            className={`online core-${coreStatus}`}
            title={
              runtimeStatus
                ? `核心运行状态：${runtimeStatus.status}`
                : "正在连接本地核心服务"
            }
          >
            <i />
            {coreStatus === "connected"
              ? "本地在线"
              : coreStatus === "connecting"
                ? "连接中"
                : coreStatus === "degraded"
                  ? "部分可用"
                  : "离线"}
          </span>
          <div className="window-actions" aria-label="窗口控制">
            <AppIconButton label="最小化" onClick={desktopBridge.minimize}>
              <Minus size={18} />
            </AppIconButton>
            <AppIconButton
              label="最大化"
              onClick={desktopBridge.toggleMaximize}
            >
              <Square size={14} />
            </AppIconButton>
            <AppIconButton label="关闭" onClick={desktopBridge.close}>
              <X size={18} />
            </AppIconButton>
          </div>
        </div>
      </header>

      {activeTab === "对话" && (
        <section className="feature-panel dialogue-page glass-panel" aria-label="对话">
          <header className="feature-heading">
            <div>
              <span className="eyebrow">今晚的对话</span>
              <h1>我在这里，慢慢说</h1>
              <p>不是重新认识你，而是从我们上次聊到的地方继续。</p>
            </div>
            <div className="dialogue-heading-actions">
              <span
                className={`presence-chip avatar-${avatarStatus?.state ?? "idle"}`}
                title={
                  avatarStatus?.renderer === "static_fallback"
                    ? avatarStatus.fallback_reason
                    : `人物渲染：${avatarStatus?.renderer ?? "读取中"}`
                }
              >
                <i />
                心屿
                {avatarStateLabels[avatarStatus?.state] ?? "安静陪伴"}
              </span>
              <button
                type="button"
                className="new-session-button"
                aria-expanded={isConversationHistoryOpen}
                onClick={() =>
                  setIsConversationHistoryOpen((isOpen) => !isOpen)
                }
              >
                <ClockCounterClockwise size={15} />
                历史
              </button>
              <button
                type="button"
                className="new-session-button"
                onClick={startNewConversation}
              >
                <Plus size={15} weight="bold" />
                新对话
              </button>
            </div>
          </header>

          {isConversationHistoryOpen && (
            <section className="conversation-history" aria-label="历史对话">
              <header>
                <strong>本机对话</strong>
                <span>{conversationList.length} 段</span>
              </header>
              <div>
                {conversationList.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    className={item.id === sessionId ? "active" : ""}
                    disabled={isConversationLoading}
                    onClick={() => openConversation(item.id)}
                  >
                    <span>
                      <strong>{item.last_message || "新的对话"}</strong>
                      <small>
                        {formatConversationTime(item.last_active_at)} ·{" "}
                        {item.message_count} 条消息
                      </small>
                    </span>
                    <CaretRight size={15} />
                  </button>
                ))}
                {conversationList.length === 0 && (
                  <p>还没有已保存的对话。发送第一条消息后会出现在这里。</p>
                )}
              </div>
            </section>
          )}

          <button
            type="button"
            className="memory-bridge"
            onClick={() => changeTab("回忆")}
          >
            <span className="bridge-icon">
              <Brain size={20} weight="duotone" />
            </span>
            <span>
              <strong>本机保存 {memories.length} 条可管理记忆</strong>
              <small>
                {memories.length
                  ? memories
                      .slice(0, 3)
                      .map((memory) => memory.title)
                      .join("、")
                  : "你明确希望我记住的事情，会出现在这里"}
              </small>
            </span>
            <CaretRight size={17} />
          </button>

          <div className="conversation-thread" aria-live="polite">
            <div className="thread-date">
              <span>今天 20:26</span>
            </div>
            {conversation.map((item) => (
              <article key={item.id} className={`message-row ${item.role}`}>
                <span className="message-avatar">
                  {item.role === "agent" ? (
                    <img src="/assets/xinyu-glass-heart-transparent.png" alt="" />
                  ) : (
                    <UserCircle size={26} weight="duotone" />
                  )}
                </span>
                <div className="message-content">
                  <p>{item.text}</p>
                  <footer>
                    <span>{item.time}</span>
                    {item.memory && (
                      <button type="button" onClick={() => changeTab("回忆")}>
                        <Sparkle size={12} weight="fill" />
                        {item.memory}
                      </button>
                    )}
                  </footer>
                </div>
              </article>
            ))}
          </div>

          <footer className="dialogue-footer">
            <LockKey size={15} />
            <span>长期记忆只保存有价值的信息，你可以随时查看、修改或忘记。</span>
          </footer>
        </section>
      )}

      {activeTab === "回忆" && (
        <section
          className={`feature-panel memory-page glass-panel ${
            isAddingMemory ? "has-memory-form" : ""
          }`}
          aria-label="回忆"
        >
          <header className="feature-heading memory-heading">
            <div>
              <span className="eyebrow">我们的记忆</span>
              <h1>她记住的，不只是聊天记录</h1>
              <p>偏好、在意的事和共同经历，会被整理成可理解、可管理的长期记忆。</p>
            </div>
            <div className="memory-heading-actions">
              <div className="memory-summary">
                <strong>
                  {memoryMode === "memories"
                    ? memories.length
                    : conversationSummaries.length}
                </strong>
                <span>
                  {memoryMode === "memories" ? "条长期记忆" : "份对话摘要"}
                </span>
              </div>
              {memoryMode === "memories" ? (
                <button
                  type="button"
                  className="add-memory-button"
                  onClick={() => setIsAddingMemory((value) => !value)}
                >
                  <Plus size={15} weight="bold" />
                  主动告诉她
                </button>
              ) : (
                <button
                  type="button"
                  className="add-memory-button"
                  onClick={generateCurrentSummary}
                  disabled={!sessionId || memoryWorkspaceBusy}
                >
                  <ArrowClockwise size={15} weight="bold" />
                  生成当前摘要
                </button>
              )}
            </div>
          </header>

          <div className="memory-segments" aria-label="回忆视图">
            <button
              type="button"
              className={memoryMode === "memories" ? "active" : ""}
              onClick={() => setMemoryMode("memories")}
            >
              长期记忆
            </button>
            <button
              type="button"
              className={memoryMode === "summaries" ? "active" : ""}
              onClick={() => setMemoryMode("summaries")}
            >
              对话摘要
            </button>
          </div>

          {memoryMode === "memories" && isAddingMemory && (
            <form className="quick-memory-form" onSubmit={addMemory}>
              <select
                value={newMemory.kind}
                onChange={(event) =>
                  setNewMemory((current) => ({
                    ...current,
                    kind: event.target.value,
                  }))
                }
                aria-label="记忆类型"
              >
                <option value="profile">关于我</option>
                <option value="preference">偏好</option>
                <option value="concern">在意</option>
                <option value="episode">点滴</option>
                <option value="commitment">约定</option>
              </select>
              <input
                autoFocus
                value={newMemory.title}
                onChange={(event) =>
                  setNewMemory((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
                placeholder="一句话标题"
                aria-label="新记忆标题"
              />
              <input
                value={newMemory.summary}
                onChange={(event) =>
                  setNewMemory((current) => ({
                    ...current,
                    summary: event.target.value,
                  }))
                }
                placeholder="希望心屿记住的具体内容"
                aria-label="新记忆内容"
              />
              <button type="submit">保存到本机</button>
              <button
                type="button"
                className="cancel-memory"
                onClick={() => setIsAddingMemory(false)}
                aria-label="取消添加记忆"
              >
                <X size={15} />
              </button>
            </form>
          )}

          {memoryMode === "memories" && (
            <>
          <div className="filter-row" aria-label="记忆筛选">
            {["全部", "点滴", "偏好", "在意", "约定"].map((filter) => (
              <button
                type="button"
                key={filter}
                className={memoryFilter === filter ? "active" : ""}
                onClick={() => setMemoryFilter(filter)}
              >
                {filter}
              </button>
            ))}
            <label className="memory-search">
              <MagnifyingGlass size={15} />
              <input
                value={memoryQuery}
                onChange={(event) => setMemoryQuery(event.target.value)}
                placeholder="搜索她记得的事"
                aria-label="搜索记忆"
              />
            </label>
          </div>

          <div className="memory-layout">
            <div className="memory-timeline">
              {filteredMemories.map((memory) => {
                const MemoryIcon = memory.icon;
                return (
                  <button
                    type="button"
                    key={memory.id}
                    className={`memory-entry ${
                      selectedMemory?.id === memory.id ? "selected" : ""
                    }`}
                    onClick={() => setSelectedMemoryId(memory.id)}
                  >
                    <span className={`memory-kind ${memory.accent}`}>
                      <MemoryIcon size={18} weight="duotone" />
                    </span>
                    <span className="memory-entry-copy">
                      <span>
                        <em>{memory.kind}</em>
                        <time>{memory.date}</time>
                      </span>
                      <strong>{memory.title}</strong>
                      <small>{memory.summary}</small>
                    </span>
                    {memory.starred && <Star size={15} weight="fill" />}
                  </button>
                );
              })}
              {filteredMemories.length === 0 && (
                <div className="memory-empty">
                  <BookOpen size={28} weight="duotone" />
                  <strong>这里还没有这类记忆</strong>
                  <span>继续相处，新的点滴会慢慢长出来。</span>
                </div>
              )}
            </div>

            {selectedMemory && (
              <aside className="memory-detail">
                <div className={`detail-icon ${selectedMemory.accent}`}>
                  {(() => {
                    const DetailIcon = selectedMemory.icon;
                    return <DetailIcon size={26} weight="duotone" />;
                  })()}
                </div>
                <span className="detail-kind">{selectedMemory.kind}</span>
                {editingMemoryId === selectedMemory.id ? (
                  <form className="memory-edit-form" onSubmit={saveMemoryEdit}>
                    <input
                      value={memoryDraft.title}
                      onChange={(event) =>
                        setMemoryDraft((draft) => ({
                          ...draft,
                          title: event.target.value,
                        }))
                      }
                      aria-label="记忆标题"
                    />
                    <textarea
                      value={memoryDraft.summary}
                      onChange={(event) =>
                        setMemoryDraft((draft) => ({
                          ...draft,
                          summary: event.target.value,
                        }))
                      }
                      aria-label="记忆内容"
                    />
                    <button type="submit">保存纠正</button>
                  </form>
                ) : (
                  <>
                    <h2>{selectedMemory.title}</h2>
                    <p>{selectedMemory.summary}</p>
                  </>
                )}
                <div className="memory-source">
                  <SealCheck size={17} weight="fill" />
                  <span>
                    <small>记忆来源</small>
                    <strong>{selectedMemory.source}</strong>
                  </span>
                </div>
                {memoryContext && (
                  <div className="memory-context">
                    <Brain size={16} weight="duotone" />
                    <span>
                      <strong>为什么记得</strong>
                      <small>{memoryContext.explanation}</small>
                      {memoryContext.source_message && (
                        <q>{memoryContext.source_message.content}</q>
                      )}
                      {memoryContext.superseded_memory && (
                        <em>
                          已替代旧记忆：
                          {memoryContext.superseded_memory.content}
                        </em>
                      )}
                    </span>
                  </div>
                )}
                <div className="detail-actions">
                  <button
                    type="button"
                    onClick={() => toggleMemoryStar(selectedMemory.id)}
                  >
                    <Star
                      size={16}
                      weight={selectedMemory.starred ? "fill" : "regular"}
                    />
                    {selectedMemory.starred ? "已珍藏" : "珍藏"}
                  </button>
                  <button
                    type="button"
                    onClick={() => startMemoryEdit(selectedMemory)}
                  >
                    <PencilSimple size={16} />
                    {editingMemoryId === selectedMemory.id ? "取消" : "纠正"}
                  </button>
                  <button
                    type="button"
                    className="danger-action"
                    onClick={() => forgetMemory(selectedMemory.id)}
                  >
                    <Trash size={16} />
                    忘记
                  </button>
                </div>
                <div className="memory-principle">
                  <LockKey size={14} />
                  <span>记忆保存在你的本地空间，只有你能管理。</span>
                </div>
              </aside>
            )}
          </div>
            </>
          )}

          {memoryMode === "summaries" && (
            <div className="summary-workspace">
              {conversationSummaries.length > 0 ? (
                <div className="summary-list">
                  {conversationSummaries.map((summary) => (
                    <article
                      key={summary.id}
                      className={`summary-entry status-${summary.status}`}
                    >
                      <header>
                        <span>
                          <strong>{summary.time}</strong>
                          <small>覆盖 {summary.messageCount} 条消息</small>
                        </span>
                        <em>{summary.statusLabel}</em>
                      </header>
                      <p>
                        {summary.content ||
                          (summary.status === "unavailable"
                            ? "尚未配置真实对话模型，原始历史窗口仍会正常使用。"
                            : summary.status === "failed"
                              ? `摘要生成失败：${summary.errorCode || "未知错误"}`
                              : "正在整理这段对话，完成后会在这里显示。")}
                      </p>
                      <footer>
                        <span>模型：{summary.model}</span>
                        <div>
                          <button
                            type="button"
                            onClick={() => rebuildConversationSummary(summary)}
                            disabled={memoryWorkspaceBusy}
                          >
                            <ArrowClockwise size={14} />
                            重建
                          </button>
                          <button
                            type="button"
                            className="danger-action"
                            onClick={() => deleteConversationSummary(summary.id)}
                            disabled={memoryWorkspaceBusy}
                          >
                            <Trash size={14} />
                            删除
                          </button>
                        </div>
                      </footer>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="summary-empty">
                  <BookOpen size={30} weight="duotone" />
                  <strong>还没有对话摘要</strong>
                  <span>长对话达到阈值后会在后台整理；也可以手动生成当前会话。</span>
                  {!sessionId && <small>先开始一段对话，才能生成摘要。</small>}
                </div>
              )}
              {memoryWorkspaceMessage && (
                <p className="memory-workspace-message" role="status">
                  {memoryWorkspaceMessage}
                </p>
              )}
            </div>
          )}
        </section>
      )}

      {activeTab === "计划" && (
        <section className="feature-panel plan-page glass-panel" aria-label="计划">
          <header className="feature-heading plan-heading">
            <div>
              <span className="eyebrow">明天 · {formatShortDate(tomorrow)}</span>
              <h1>把想做的事，变成一起完成的日常</h1>
              <p>你的个人计划由你决定，心屿负责陪你拆解、提醒和复盘。</p>
            </div>
            <button
              type="button"
              className="add-plan-button"
              onClick={openPlanForm}
            >
              <Plus size={17} weight="bold" />
              添加计划
            </button>
          </header>

          <div className="plan-overview">
            <div>
              <span className="overview-icon">
                <Target size={20} weight="duotone" />
              </span>
              <span>
                <small>明日进度</small>
                <strong>
                  {completedPlans}/{planItems.length} 已完成
                </strong>
              </span>
            </div>
            <div className="progress-track" aria-hidden="true">
              <i
                style={{
                  width: `${Math.max(
                    6,
                    (completedPlans / Math.max(1, planItems.length)) * 100,
                  )}%`,
                }}
              />
            </div>
            <span className="companion-promise">
              <Bell size={16} weight="duotone" />
              我会在合适的时候提醒你
            </span>
          </div>

          {isAddingPlan && (
            <form className="quick-plan-form" onSubmit={addPlan}>
              {editingPlanId ? (
                <PencilSimple size={17} />
              ) : (
                <Plus size={17} />
              )}
              <input
                autoFocus
                value={newPlan.title}
                onChange={(event) =>
                  setNewPlan((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
                placeholder="例如：晚上散步 20 分钟"
                aria-label={editingPlanId ? "编辑计划内容" : "新计划内容"}
              />
              <select
                value={newPlan.category}
                onChange={(event) =>
                  setNewPlan((current) => ({
                    ...current,
                    category: event.target.value,
                  }))
                }
                aria-label="计划分类"
              >
                <option value="work">工作</option>
                <option value="life">生活</option>
                <option value="promise">约定</option>
              </select>
              <input
                type="datetime-local"
                value={newPlan.dueAt}
                onChange={(event) =>
                  setNewPlan((current) => ({
                    ...current,
                    dueAt: event.target.value,
                  }))
                }
                aria-label="计划时间"
              />
              <label className="plan-reminder-option">
                <input
                  type="checkbox"
                  checked={newPlan.remind}
                  disabled={!newPlan.dueAt}
                  onChange={(event) =>
                    setNewPlan((current) => ({
                      ...current,
                      remind: event.target.checked,
                    }))
                  }
                />
                提前 15 分钟
              </label>
              <button type="submit">
                {editingPlanId ? "保存修改" : "保存"}
              </button>
              <button
                type="button"
                className="cancel-plan"
                onClick={() => {
                  setIsAddingPlan(false);
                  setEditingPlanId(null);
                }}
                aria-label={editingPlanId ? "取消编辑" : "取消添加"}
              >
                <X size={15} />
              </button>
            </form>
          )}

          <div className="plan-layout">
            <div className="plan-main">
              <div className="filter-row plan-filters">
                {["全部", "工作", "生活", "约定"].map((filter) => (
                  <button
                    type="button"
                    key={filter}
                    className={planFilter === filter ? "active" : ""}
                    onClick={() => setPlanFilter(filter)}
                  >
                    {filter}
                  </button>
                ))}
              </div>
              <div className="schedule-list">
                {filteredPlans.map((item) => (
                  <article
                    key={item.id}
                    className={`schedule-item ${item.done ? "done" : ""}`}
                  >
                    <button
                      type="button"
                      className="schedule-check"
                      aria-label={item.done ? "标记为未完成" : "标记为已完成"}
                      aria-pressed={item.done}
                      onClick={() => togglePlan(item.id)}
                    >
                      {item.done && <Check size={13} weight="bold" />}
                    </button>
                    <time>{item.time}</time>
                    <span className="schedule-copy">
                      <strong>{item.title}</strong>
                      <small>{item.meta}</small>
                    </span>
                    <span className="plan-actions">
                      <button
                        type="button"
                        className="plan-edit"
                        aria-label={`编辑计划：${item.title}`}
                        title="编辑计划"
                        onClick={() => startPlanEdit(item)}
                      >
                        <PencilSimple size={14} />
                      </button>
                      <button
                        type="button"
                        className="plan-delete"
                        aria-label={`删除计划：${item.title}`}
                        title="删除计划"
                        onClick={() => deletePlan(item.id)}
                      >
                        <Trash size={14} />
                      </button>
                    </span>
                  </article>
                ))}
              </div>
            </div>

            <aside className="plan-companion-card">
              <span className="eyebrow">心屿的建议</span>
              <span className="suggestion-orb">
                <Compass size={28} weight="duotone" />
              </span>
              <h2>会议之后，留一点缓冲</h2>
              <p>
                你最近连续几天都排得很满。午休后那段散步，我先替你留着，不往里面塞别的事。
              </p>
              <button
                type="button"
                className={hasSuggestedWalk ? "accepted" : ""}
                onClick={acceptPlanSuggestion}
                disabled={hasSuggestedWalk}
              >
                <CheckCircle
                  size={16}
                  weight={hasSuggestedWalk ? "fill" : "duotone"}
                />
                {hasSuggestedWalk ? "已加入明日节奏" : "接受这个安排"}
              </button>
              {notifications.length > 0 && (
                <div className="notification-inbox">
                  <span>
                    <Bell size={14} weight="duotone" />
                    未读提醒 {notifications.length}
                  </span>
                  {notifications.slice(0, 2).map((notification) => (
                    <button
                      type="button"
                      key={notification.id}
                      onClick={() => acknowledgeNotification(notification.id)}
                      title="标记为已读"
                    >
                      <strong>
                        {notification.payload?.task?.title ??
                          notification.payload?.message ??
                          "提醒"}
                      </strong>
                      <small>点击归档</small>
                    </button>
                  ))}
                </div>
              )}
              <div className="plan-tags">
                <span>
                  <Briefcase size={14} />
                  工作 {workPlanCount} 项
                </span>
                <span>
                  <Heart size={14} />
                  约定 {promisePlanCount} 项
                </span>
              </div>
            </aside>
          </div>
        </section>
      )}

      {activeTab === "更多" && (
        <section
          className="feature-panel settings-page glass-panel"
          aria-label="设置与本地数据"
        >
          <header className="feature-heading settings-heading">
            <div>
              <span className="eyebrow">本地控制中心</span>
              <h1>运行、隐私与数据</h1>
              <p>模型和数据都按组件展示，不把未启动的能力伪装成在线。</p>
            </div>
            <span className={`presence-chip status-${coreStatus}`}>
              <i />
              {coreStatus === "connected" ? "核心服务已连接" : "核心服务未连接"}
            </span>
          </header>

          <div className="settings-grid">
            <section className="settings-card runtime-settings">
              <div className="settings-card-title">
                <Waveform size={19} weight="duotone" />
                <span>
                  <strong>运行组件</strong>
                  <small>真实状态来自本地 Core API</small>
                </span>
              </div>
              {systemCapabilities && (
                <div className="hardware-summary">
                  <Cpu size={18} weight="duotone" />
                  <span>
                    <strong>
                      {systemCapabilities.gpus[0]?.name ?? "未检测到 NVIDIA GPU"}
                    </strong>
                    <small>
                      {systemCapabilities.memory_gb} GB 内存 ·{" "}
                      {profileLabels[systemCapabilities.recommended_profile]}
                    </small>
                  </span>
                </div>
              )}
              <div className="runtime-component-list">
                {(runtimeStatus?.components ?? []).map((component) => (
                  <div key={component.id} className="runtime-component">
                    <span>
                      <strong>{component.kind.toUpperCase()}</strong>
                      <small>{component.detail}</small>
                    </span>
                    <em className={`component-${component.status}`}>
                      {component.status === "ready"
                        ? "就绪"
                        : component.status === "degraded"
                          ? "降级"
                          : "未安装"}
                    </em>
                  </div>
                ))}
                {!runtimeStatus && (
                  <div className="runtime-component">
                    <span>
                      <strong>CORE</strong>
                      <small>正在读取本地运行状态</small>
                    </span>
                    <em className="component-unavailable">连接中</em>
                  </div>
                )}
              </div>
              <div className="memory-index-status">
                <span>
                  <Brain size={17} weight="duotone" />
                  <span>
                    <strong>语义记忆索引</strong>
                    <small>{memoryIndex?.model ?? "BAAI/bge-small-zh-v1.5"}</small>
                  </span>
                </span>
                <div>
                  <span>
                    已索引 {memoryIndex?.indexed_count ?? 0} · 待处理{" "}
                    {memoryIndex?.pending_count ?? memories.length}
                  </span>
                  <em className={`component-${memoryIndex?.status ?? "disabled"}`}>
                    {memoryIndexStatusLabels[memoryIndex?.status] ?? "读取中"}
                  </em>
                </div>
                {memoryIndex?.last_error && (
                  <small>最近状态：{memoryIndex.last_error}</small>
                )}
                <button
                  type="button"
                  onClick={rebuildMemoryIndex}
                  disabled={memoryWorkspaceBusy || coreStatus !== "connected"}
                >
                  <ArrowClockwise size={14} />
                  重建索引
                </button>
              </div>
              <div className="microphone-settings">
                <label htmlFor="voice-input-device">
                  <Microphone size={17} weight="duotone" />
                  <span>
                    <strong>语音输入</strong>
                    <small>仅在点击语音按钮后启用麦克风</small>
                  </span>
                </label>
                <div>
                  <select
                    id="voice-input-device"
                    value={selectedMicrophone}
                    onChange={selectMicrophone}
                    disabled={!microphoneDevices.length}
                  >
                    <option value="">系统默认麦克风</option>
                    {microphoneDevices.map((device) => (
                      <option key={device.id} value={device.id}>
                        {device.label}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={detectMicrophones}>
                    检测麦克风
                  </button>
                </div>
              </div>
            </section>

            <section className="settings-card privacy-settings">
              <div className="settings-card-title">
                <LockKey size={19} weight="duotone" />
                <span>
                  <strong>隐私与主动陪伴</strong>
                  <small>设置保存在本机 SQLite</small>
                </span>
              </div>
              <button
                type="button"
                className="setting-row"
                onClick={() => toggleSetting("privacy.memory_enabled")}
                aria-pressed={settings["privacy.memory_enabled"]}
              >
                <span>
                  <Brain size={17} />
                  <span>
                    <strong>长期记忆</strong>
                    <small>只提取用户明确表达的高置信信息</small>
                  </span>
                </span>
                <i
                  className={
                    settings["privacy.memory_enabled"] ? "switch-on" : ""
                  }
                />
              </button>
              <button
                type="button"
                className="setting-row"
                onClick={() => toggleSetting("privacy.proactive_enabled")}
                aria-pressed={settings["privacy.proactive_enabled"]}
              >
                <span>
                  <Bell size={17} />
                  <span>
                    <strong>主动陪伴</strong>
                    <small>统一开关，遵守安静时段与每日频率上限</small>
                  </span>
                </span>
                <i
                  className={
                    settings["privacy.proactive_enabled"] ? "switch-on" : ""
                  }
                />
              </button>
              <button
                type="button"
                className="setting-row"
                onClick={() => toggleSetting("proactive.checkin_enabled")}
                aria-pressed={settings["proactive.checkin_enabled"]}
              >
                <span>
                  <Heart size={17} />
                  <span>
                    <strong>温柔问候</strong>
                    <small>仅在已有互动且长时间未交流时触发，每日最多 2 次</small>
                  </span>
                </span>
                <i
                  className={
                    settings["proactive.checkin_enabled"] ? "switch-on" : ""
                  }
                />
              </button>
              <button
                type="button"
                className="setting-row"
                onClick={toggleAutostart}
                aria-pressed={autostartEnabled}
              >
                <span>
                  <ClockCounterClockwise size={17} />
                  <span>
                    <strong>开机启动</strong>
                    <small>
                      {isDesktopRuntime()
                        ? "由系统启动项管理，可随时关闭"
                        : "桌面安装版可用，网页演示不会修改系统"}
                    </small>
                  </span>
                </span>
                <i className={autostartEnabled ? "switch-on" : ""} />
              </button>
              <div className="quality-row">
                <SealCheck size={17} weight="fill" />
                <span>
                  <strong>人物质量</strong>
                  <small>高质量写实模式 · 不使用 2.5D 降级</small>
                </span>
                <em>{settings["avatar.quality"] === "high" ? "高质量" : "兼容"}</em>
              </div>
            </section>

            <form
              className="settings-card persona-settings"
              onSubmit={savePersona}
            >
              <div className="settings-card-title">
                <UserCircle size={19} weight="duotone" />
                <span>
                  <strong>陪伴人格</strong>
                  <small>每次保存都会创建可追溯的新版本</small>
                </span>
              </div>
              <div className="persona-form-fields">
                <label>
                  <span>称呼</span>
                  <input
                    value={personaDraft.name}
                    maxLength={40}
                    onChange={(event) =>
                      setPersonaDraft((current) => ({
                        ...current,
                        name: event.target.value,
                      }))
                    }
                  />
                </label>
                <label>
                  <span>性格与边界</span>
                  <textarea
                    value={personaDraft.background}
                    maxLength={800}
                    onChange={(event) =>
                      setPersonaDraft((current) => ({
                        ...current,
                        background: event.target.value,
                      }))
                    }
                  />
                </label>
                <button type="submit">
                  保存人格版本
                </button>
              </div>
            </form>

            <section className="settings-card note-settings">
              <div className="settings-card-title">
                <MoonStars size={19} weight="duotone" />
                <span>
                  <strong>晚安心语</strong>
                  <small>主页右侧主动留言</small>
                </span>
              </div>
              <textarea
                value={draftNote}
                onChange={(event) => setDraftNote(event.target.value)}
                maxLength={76}
                aria-label="晚安心语内容"
              />
              <button type="button" className="save-button" onClick={saveNote}>
                保存到本机
              </button>
            </section>

            <section className="settings-card data-settings">
              <div className="settings-card-title">
                <UserCircle size={19} weight="duotone" />
                <span>
                  <strong>我的数据</strong>
                  <small>对话、记忆、计划和人格版本</small>
                </span>
              </div>
              <button
                type="button"
                className="data-action"
                onClick={createLocalBackup}
              >
                <ClockCounterClockwise size={17} />
                创建本地数据库快照
              </button>
              {latestBackup && (
                <>
                  <small className="backup-summary">
                    最近备份：{latestBackup.name}
                  </small>
                  <button
                    type="button"
                    className={`data-action ${
                      confirmingRestore ? "restore-confirming" : ""
                    }`}
                    onClick={restoreLatestBackup}
                  >
                    <ClockCounterClockwise size={17} />
                    {confirmingRestore ? "确认恢复" : "恢复最近备份"}
                  </button>
                  {confirmingRestore && (
                    <button
                      type="button"
                      className="cancel-delete"
                      onClick={() => {
                        setConfirmingRestore(false);
                        setSettingsMessage("");
                      }}
                    >
                      取消恢复
                    </button>
                  )}
                </>
              )}
              <button
                type="button"
                className="data-action"
                onClick={exportLocalData}
              >
                <BookOpen size={17} />
                导出完整 JSON
              </button>
              <button
                type="button"
                className="data-action"
                onClick={exportDiagnostics}
              >
                <Cpu size={17} />
                导出脱敏诊断报告
              </button>
              <input
                ref={importInputRef}
                type="file"
                accept="application/json,.json"
                className="visually-hidden"
                onChange={selectImportFile}
              />
              <button
                type="button"
                className="data-action"
                onClick={() => importInputRef.current?.click()}
              >
                <Plus size={17} />
                选择 JSON 导入
              </button>
              {pendingImport && (
                <>
                  <small className="backup-summary">
                    待导入：{pendingImport.name}
                  </small>
                  <button
                    type="button"
                    className="data-action restore-confirming"
                    onClick={importLocalData}
                  >
                    <CheckCircle size={17} />
                    确认导入
                  </button>
                  <button
                    type="button"
                    className="cancel-delete"
                    onClick={() => {
                      setPendingImport(null);
                      setSettingsMessage("");
                    }}
                  >
                    取消导入
                  </button>
                </>
              )}
              <button
                type="button"
                className={`data-action danger-action ${
                  confirmingDataDelete ? "confirming" : ""
                }`}
                onClick={deleteLocalData}
              >
                <Trash size={17} />
                {confirmingDataDelete ? "确认清除" : "清除本地用户数据"}
              </button>
              {confirmingDataDelete && (
                <button
                  type="button"
                  className="cancel-delete"
                  onClick={() => {
                    setConfirmingDataDelete(false);
                    setSettingsMessage("");
                  }}
                >
                  取消清除
                </button>
              )}
            </section>
          </div>

          {settingsMessage && (
            <footer className="settings-message" role="status">
              {settingsMessage}
            </footer>
          )}
        </section>
      )}

      {activeTab === "此刻" && (
      <aside className="right-rail" aria-label="陪伴信息">
        <button
          type="button"
          className="memory-card glass-panel"
          onClick={() => changeTab("回忆")}
        >
          <div className="card-heading">
            <span>我们的点滴</span>
            <ArrowRight size={17} />
          </div>
          <div className="memory-body">
            <img src="/assets/movie-night-memory.png" alt="一起看电影的夜晚" />
            <div>
              <strong>{memories[0]?.title ?? "还没有共同点滴"}</strong>
              <span>{memories[0]?.date ?? "从第一次真诚对话开始"}</span>
            </div>
          </div>
        </button>

        <section className="todo-card glass-panel">
          <div className="card-heading">
            <span>明日清单 · {remainingTasks}</span>
          </div>
          <div className="task-list">
            {tomorrowTasks.map((task) => (
              <label key={task.id} className={task.done ? "done" : ""}>
                <input
                  type="checkbox"
                  checked={task.done}
                  onChange={() => togglePlan(task.id)}
                />
                <span className="check-control" aria-hidden="true">
                  {task.done && <Check size={12} weight="bold" />}
                </span>
                <span>{task.title}</span>
              </label>
            ))}
            {!tomorrowTasks.length && (
              <span className="empty-task-hint">明天暂时没有待办</span>
            )}
          </div>
        </section>

        <section className="note-card glass-panel">
          <div className="card-heading note-heading">
            <span>晚上好呀</span>
            <MoonStars size={19} weight="fill" />
          </div>
          <p>{note}</p>
          <Heart className="note-heart" size={29} weight="duotone" />
        </section>
      </aside>
      )}

      {lastMessage && (
        <div className="reply-toast" role="status">
          <span>
            {lastMessageSource}：{lastMessage}
          </span>
          <strong>
            {lastMessageSource === "你说" ? "我在听，慢慢说。" : "状态已更新"}
          </strong>
          <button type="button" onClick={() => setLastMessage("")} aria-label="关闭">
            <X size={15} />
          </button>
        </div>
      )}

      <section className="control-dock glass-panel" aria-label="陪伴控制台">
        <div className="music-zone">
          <audio
            ref={audioRef}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={handleTrackEnded}
            onTimeUpdate={syncTrackProgress}
          />
          <input
            ref={musicInputRef}
            className="music-file-input"
            type="file"
            accept="audio/*"
            multiple
            onChange={loadMusic}
            aria-label="选择本机音乐文件或歌单"
          />
          <button
            type="button"
            className="album-cover-button"
            onClick={chooseMusic}
            aria-label="选择本机音乐"
          >
            <img
              className="album-cover"
              src="/assets/night-song-cover.png"
              alt=""
            />
          </button>
          <div className="track-meta">
            <strong>{trackName}</strong>
            <span>{trackArtist}</span>
            <div className="track-line">
              <Waveform size={31} weight="thin" />
              <input
                type="range"
                min="0"
                max="100"
                value={progress}
                onChange={seekTrack}
                aria-label="播放进度"
                disabled={!trackUrl}
              />
            </div>
          </div>
          <div className="music-actions">
            <AppIconButton label="上一首" onClick={previousTrack}>
              <SkipBack size={18} weight="fill" />
            </AppIconButton>
            <AppIconButton
              label={isPlaying ? "暂停" : "播放"}
              className="primary-control"
              onClick={togglePlayback}
              pressed={isPlaying}
            >
              {isPlaying ? (
                <Pause size={18} weight="fill" />
              ) : (
                <Play size={18} weight="fill" />
              )}
            </AppIconButton>
            <AppIconButton label="下一首" onClick={nextTrack}>
              <SkipForward size={18} weight="fill" />
            </AppIconButton>
            <AppIconButton
              label={isMuted ? "取消静音" : "静音"}
              onClick={toggleMute}
              pressed={isMuted}
            >
              <SpeakerHigh size={18} />
            </AppIconButton>
          </div>
        </div>

        <form className="conversation-zone" onSubmit={sendMessage}>
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={
              isSending
                ? "心屿正在想…"
                : isListening
                  ? voiceStatusLabels[voiceStatus] ?? "正在聆听…"
                  : "今晚想聊些什么？"
            }
            aria-label="对话输入"
            disabled={isSending}
          />
          <AppIconButton
            label={isListening ? "停止聆听" : "开始语音输入"}
            className={`voice-button ${isListening ? "listening" : ""}`}
            onClick={toggleListening}
            pressed={isListening}
            title={voiceStatusLabels[voiceStatus] ?? "开始语音输入"}
            style={{
              "--microphone-glow": `${15 + Math.min(microphoneLevel * 10, 1) * 12}px`,
              "--microphone-glow-strong": `${24 + Math.min(microphoneLevel * 10, 1) * 20}px`,
            }}
          >
            <Microphone size={24} weight="fill" />
          </AppIconButton>
        </form>

        <button
          type="button"
          className="mood-zone"
          onClick={cycleMood}
          aria-label="切换此刻心情"
        >
          <img src="/assets/mood-orb.png" alt="" />
          <span>
            <small>此刻心情</small>
            <strong>{currentMood.label}</strong>
            <em>{currentMood.hint}</em>
          </span>
        </button>
      </section>
    </main>
  );
}
