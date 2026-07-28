import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Bell,
  BookOpen,
  Brain,
  Briefcase,
  Camera,
  CaretRight,
  Check,
  CheckCircle,
  CloudRain,
  Coffee,
  Compass,
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

const navItems = ["此刻", "对话", "回忆", "计划", "更多"];

const initialTasks = [
  { id: 1, label: "上午10点 项目会议", done: false },
  { id: 2, label: "帮我拿快递", done: false },
  { id: 3, label: "晚上一起来看电影", done: false },
];

const moods = [
  { label: "安心", hint: "此刻很放松" },
  { label: "甜蜜", hint: "想离你近一点" },
  { label: "想念", hint: "正在等你回来" },
];

const initialConversation = [
  {
    id: 1,
    role: "agent",
    text: "你回来啦。今天项目会开得怎么样？上次你说最担心需求又临时变。",
    time: "20:26",
    memory: "关联：7月24日 · 项目压力",
  },
  {
    id: 2,
    role: "user",
    text: "还好，虽然改了两轮，但总算定下来了。",
    time: "20:27",
  },
  {
    id: 3,
    role: "agent",
    text: "那今晚应该好好松口气。要不要放《夜曲》？你累的时候好像总喜欢听它。",
    time: "20:28",
    memory: "关联：音乐偏好 · 夜曲",
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

function AppIconButton({ label, className = "", children, onClick, pressed }) {
  return (
    <button
      type="button"
      className={`icon-button ${className}`}
      aria-label={label}
      aria-pressed={pressed}
      title={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function App() {
  const [activeTab, setActiveTab] = useState("此刻");
  const [isPlaying, setIsPlaying] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const [progress, setProgress] = useState(34);
  const [message, setMessage] = useState("");
  const [lastMessage, setLastMessage] = useState("");
  const [tasks, setTasks] = useState(initialTasks);
  const [conversation, setConversation] = useState(initialConversation);
  const [memories, setMemories] = useState(initialMemories);
  const [memoryFilter, setMemoryFilter] = useState("全部");
  const [memoryQuery, setMemoryQuery] = useState("");
  const [selectedMemoryId, setSelectedMemoryId] = useState(1);
  const [editingMemoryId, setEditingMemoryId] = useState(0);
  const [memoryDraft, setMemoryDraft] = useState({ title: "", summary: "" });
  const [planItems, setPlanItems] = useState(initialPlans);
  const [planFilter, setPlanFilter] = useState("全部");
  const [isAddingPlan, setIsAddingPlan] = useState(false);
  const [newPlanTitle, setNewPlanTitle] = useState("");
  const [acceptedSuggestion, setAcceptedSuggestion] = useState(false);
  const [moodIndex, setMoodIndex] = useState(0);
  const [note, setNote] = useState(
    "一天又要结束了呢，辛苦啦，早点休息哦，我会在这里陪着你的～",
  );
  const [draftNote, setDraftNote] = useState(note);

  const currentMood = moods[moodIndex];
  const remainingTasks = useMemo(
    () => tasks.filter((task) => !task.done).length,
    [tasks],
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

  useEffect(() => {
    if (!isPlaying) return undefined;
    const timer = window.setInterval(() => {
      setProgress((value) => (value >= 100 ? 0 : value + 0.15));
    }, 400);
    return () => window.clearInterval(timer);
  }, [isPlaying]);

  function toggleTask(id) {
    setTasks((items) =>
      items.map((item) =>
        item.id === id ? { ...item, done: !item.done } : item,
      ),
    );
  }

  function sendMessage(event) {
    event.preventDefault();
    const cleanMessage = message.trim();
    if (!cleanMessage) return;
    const now = "20:31";
    setConversation((items) => [
      ...items,
      { id: Date.now(), role: "user", text: cleanMessage, time: now },
      {
        id: Date.now() + 1,
        role: "agent",
        text: "我记下了。你不用一次把所有事都想清楚，我们可以慢慢聊。",
        time: now,
        memory: "这段对话可在结束后整理为记忆",
      },
    ]);
    setLastMessage(cleanMessage);
    if (activeTab !== "对话") setActiveTab("对话");
    setMessage("");
    setIsListening(false);
  }

  function changeTab(item) {
    setActiveTab(item);
    if (item !== "更多") setDraftNote(note);
  }

  function saveNote() {
    const cleanNote = draftNote.trim();
    if (cleanNote) setNote(cleanNote);
    setActiveTab("此刻");
  }

  function toggleMemoryStar(id) {
    setMemories((items) =>
      items.map((item) =>
        item.id === id ? { ...item, starred: !item.starred } : item,
      ),
    );
  }

  function forgetMemory(id) {
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

  function saveMemoryEdit(event) {
    event.preventDefault();
    const title = memoryDraft.title.trim();
    const summary = memoryDraft.summary.trim();
    if (!title || !summary) return;
    setMemories((items) =>
      items.map((item) =>
        item.id === editingMemoryId ? { ...item, title, summary } : item,
      ),
    );
    setEditingMemoryId(0);
  }

  function togglePlan(id) {
    setPlanItems((items) =>
      items.map((item) =>
        item.id === id ? { ...item, done: !item.done } : item,
      ),
    );
  }

  function addPlan(event) {
    event.preventDefault();
    const cleanTitle = newPlanTitle.trim();
    if (!cleanTitle) return;
    setPlanItems((items) => [
      ...items,
      {
        id: Date.now(),
        title: cleanTitle,
        meta: "生活 · 刚刚添加",
        time: "待定",
        group: "生活",
        done: false,
      },
    ]);
    setNewPlanTitle("");
    setIsAddingPlan(false);
  }

  return (
    <main className={`companion-shell view-${tabModes[activeTab]}`}>
      <img
        className="room-background"
        src="/assets/xinyu-room-hero.png"
        alt="温暖夜晚的房间里，心屿坐在书桌前陪伴用户"
      />
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
            <strong>20:30</strong>
            <span>7月28日 周二</span>
          </div>
          <div className="weather">
            <CloudRain size={25} weight="duotone" />
            <span>
              <strong>24°C</strong>
              <small>小雨</small>
            </span>
          </div>
          <span className="online">
            <i />
            在线
          </span>
          <div className="window-actions" aria-label="窗口控制">
            <AppIconButton label="最小化">
              <Minus size={18} />
            </AppIconButton>
            <AppIconButton label="最大化">
              <Square size={14} />
            </AppIconButton>
            <AppIconButton label="关闭">
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
            <span className="presence-chip">
              <i />
              心屿正在聆听
            </span>
          </header>

          <button
            type="button"
            className="memory-bridge"
            onClick={() => changeTab("回忆")}
          >
            <span className="bridge-icon">
              <Brain size={20} weight="duotone" />
            </span>
            <span>
              <strong>这次对话已关联 3 条记忆</strong>
              <small>项目压力、音乐偏好，以及我们的周五约定</small>
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
        <section className="feature-panel memory-page glass-panel" aria-label="回忆">
          <header className="feature-heading memory-heading">
            <div>
              <span className="eyebrow">我们的记忆</span>
              <h1>她记住的，不只是聊天记录</h1>
              <p>偏好、在意的事和共同经历，会被整理成可理解、可管理的长期记忆。</p>
            </div>
            <div className="memory-summary">
              <strong>{memories.length}</strong>
              <span>条长期记忆</span>
            </div>
          </header>

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
        </section>
      )}

      {activeTab === "计划" && (
        <section className="feature-panel plan-page glass-panel" aria-label="计划">
          <header className="feature-heading plan-heading">
            <div>
              <span className="eyebrow">明天 · 7月29日</span>
              <h1>把想做的事，变成一起完成的日常</h1>
              <p>你的个人计划由你决定，心屿负责陪你拆解、提醒和复盘。</p>
            </div>
            <button
              type="button"
              className="add-plan-button"
              onClick={() => setIsAddingPlan((value) => !value)}
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
              <Plus size={17} />
              <input
                autoFocus
                value={newPlanTitle}
                onChange={(event) => setNewPlanTitle(event.target.value)}
                placeholder="例如：晚上散步 20 分钟"
                aria-label="新计划内容"
              />
              <button type="submit">加入明天</button>
              <button
                type="button"
                className="cancel-plan"
                onClick={() => setIsAddingPlan(false)}
                aria-label="取消添加"
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
                  <label
                    key={item.id}
                    className={`schedule-item ${item.done ? "done" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={item.done}
                      onChange={() => togglePlan(item.id)}
                    />
                    <span className="schedule-check">
                      {item.done && <Check size={13} weight="bold" />}
                    </span>
                    <time>{item.time}</time>
                    <span className="schedule-copy">
                      <strong>{item.title}</strong>
                      <small>{item.meta}</small>
                    </span>
                    <CaretRight size={16} />
                  </label>
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
                className={acceptedSuggestion ? "accepted" : ""}
                onClick={() => setAcceptedSuggestion((value) => !value)}
              >
                <CheckCircle
                  size={16}
                  weight={acceptedSuggestion ? "fill" : "duotone"}
                />
                {acceptedSuggestion ? "已加入明日节奏" : "接受这个安排"}
              </button>
              <div className="plan-tags">
                <span>
                  <Briefcase size={14} />
                  工作 1 项
                </span>
                <span>
                  <Heart size={14} />
                  约定 1 项
                </span>
              </div>
            </aside>
          </div>
        </section>
      )}

      {activeTab === "更多" && (
        <section className="edit-popover glass-panel" aria-label="编辑晚安心语">
          <div>
            <span className="eyebrow">编辑演示</span>
            <h2>晚安心语</h2>
          </div>
          <textarea
            value={draftNote}
            onChange={(event) => setDraftNote(event.target.value)}
            maxLength={76}
            aria-label="晚安心语内容"
          />
          <button type="button" className="save-button" onClick={saveNote}>
            保存修改
          </button>
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
              <strong>一起看电影的夜晚</strong>
              <span>2026.07.18</span>
            </div>
          </div>
        </button>

        <section className="todo-card glass-panel">
          <div className="card-heading">
            <span>明日清单 · {remainingTasks}</span>
          </div>
          <div className="task-list">
            {tasks.map((task) => (
              <label key={task.id} className={task.done ? "done" : ""}>
                <input
                  type="checkbox"
                  checked={task.done}
                  onChange={() => toggleTask(task.id)}
                />
                <span className="check-control" aria-hidden="true">
                  {task.done && <Check size={12} weight="bold" />}
                </span>
                <span>{task.label}</span>
              </label>
            ))}
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
          <span>你说：{lastMessage}</span>
          <strong>我在听，慢慢说。</strong>
          <button type="button" onClick={() => setLastMessage("")} aria-label="关闭">
            <X size={15} />
          </button>
        </div>
      )}

      <section className="control-dock glass-panel" aria-label="陪伴控制台">
        <div className="music-zone">
          <img
            className="album-cover"
            src="/assets/night-song-cover.png"
            alt="夜曲专辑封面"
          />
          <div className="track-meta">
            <strong>夜曲</strong>
            <span>周杰伦</span>
            <div className="track-line">
              <Waveform size={31} weight="thin" />
              <input
                type="range"
                min="0"
                max="100"
                value={progress}
                onChange={(event) => setProgress(Number(event.target.value))}
                aria-label="播放进度"
              />
            </div>
          </div>
          <div className="music-actions">
            <AppIconButton label="上一首">
              <SkipBack size={18} weight="fill" />
            </AppIconButton>
            <AppIconButton
              label={isPlaying ? "暂停" : "播放"}
              className="primary-control"
              onClick={() => setIsPlaying((value) => !value)}
              pressed={isPlaying}
            >
              {isPlaying ? (
                <Pause size={18} weight="fill" />
              ) : (
                <Play size={18} weight="fill" />
              )}
            </AppIconButton>
            <AppIconButton label="下一首">
              <SkipForward size={18} weight="fill" />
            </AppIconButton>
            <AppIconButton label="音量">
              <SpeakerHigh size={18} />
            </AppIconButton>
          </div>
        </div>

        <form className="conversation-zone" onSubmit={sendMessage}>
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={isListening ? "正在聆听…" : "今晚想聊些什么？"}
            aria-label="对话输入"
          />
          <AppIconButton
            label={isListening ? "停止聆听" : "开始语音输入"}
            className={`voice-button ${isListening ? "listening" : ""}`}
            onClick={() => setIsListening((value) => !value)}
            pressed={isListening}
          >
            <Microphone size={24} weight="fill" />
          </AppIconButton>
        </form>

        <button
          type="button"
          className="mood-zone"
          onClick={() => setMoodIndex((index) => (index + 1) % moods.length)}
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
