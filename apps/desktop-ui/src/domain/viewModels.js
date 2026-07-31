import {
  Brain,
  Camera,
  Coffee,
  Flag,
} from "@phosphor-icons/react";

const memoryPresentation = {
  profile: { kind: "在意", icon: Brain, accent: "violet" },
  preference: { kind: "偏好", icon: Coffee, accent: "amber" },
  concern: { kind: "在意", icon: Brain, accent: "violet" },
  episode: { kind: "点滴", icon: Camera, accent: "rose" },
  commitment: { kind: "约定", icon: Flag, accent: "blue" },
};

const planGroups = {
  work: "工作",
  life: "生活",
  promise: "约定",
};

export const profileLabels = {
  high_quality_24gb: "24GB 高质量档",
  high_quality_16gb: "16GB 高质量档",
  balanced_10gb: "10GB 均衡档",
  cpu_compatibility: "CPU 兼容档",
};

export function formatClock(value) {
  if (!value) return "待定";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
    .format(new Date(value))
    .replaceAll("/", ".");
}

export function formatCalendarDate(value) {
  const date = new Date(value);
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${date.getMonth() + 1}月${date.getDate()}日 ${weekdays[date.getDay()]}`;
}

export function formatShortDate(value) {
  const date = new Date(value);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

export function formatConversationTime(value) {
  if (!value) return "";
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return `今天 ${formatClock(date)}`;
  }
  return `${formatShortDate(date)} ${formatClock(date)}`;
}

export function toMessageView(message) {
  return {
    id: message.id,
    role: message.role === "assistant" ? "agent" : message.role,
    text: message.content,
    time: formatClock(message.created_at),
    memory:
      message.metadata?.provider && message.role === "assistant"
        ? `本地回复 · ${message.metadata.provider}`
        : undefined,
  };
}

export function toMemoryView(memory) {
  const presentation =
    memoryPresentation[memory.kind] ?? memoryPresentation.episode;
  return {
    id: memory.id,
    kind: presentation.kind,
    backendKind: memory.kind,
    icon: presentation.icon,
    title: memory.title,
    summary: memory.content,
    date: formatDate(memory.updated_at),
    source:
      memory.source === "user_explicit"
        ? "你主动告诉我 · 已确认"
        : "本地记忆整理 · 待你确认",
    accent: presentation.accent,
    starred: memory.starred,
    userConfirmed: memory.user_confirmed,
    sourceMessageId: memory.source_message_id,
    supersedesId: memory.supersedes_id,
  };
}

export function toPlanView(plan) {
  const reminderText = plan.reminder_at ? "已设提醒" : "不提醒";
  return {
    id: plan.id,
    title: plan.title,
    meta: `${planGroups[plan.category] ?? "生活"} · ${
      plan.description || reminderText
    }`,
    time: formatClock(plan.due_at),
    group: planGroups[plan.category] ?? "生活",
    category: plan.category,
    dueAt: plan.due_at,
    reminderAt: plan.reminder_at,
    done: plan.status === "completed",
  };
}
