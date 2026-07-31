import assert from "node:assert/strict";
import test from "node:test";

import {
  formatCalendarDate,
  formatConversationTime,
  formatClock,
  formatShortDate,
  profileLabels,
  toMessageView,
  toMemoryView,
  toPlanView,
} from "../src/domain/viewModels.js";

test("maps backend memories to user-managed presentation data", () => {
  const view = toMemoryView({
    id: "memory-1",
    kind: "preference",
    title: "你的偏好",
    content: "喜欢乌龙茶",
    source: "user_explicit",
    updated_at: "2026-07-29T10:00:00Z",
    starred: true,
    user_confirmed: true,
  });

  assert.equal(view.kind, "偏好");
  assert.equal(view.summary, "喜欢乌龙茶");
  assert.equal(view.source, "你主动告诉我 · 已确认");
  assert.equal(view.accent, "amber");
  assert.equal(view.starred, true);
});

test("maps plans without a due time to a stable local view", () => {
  const view = toPlanView({
    id: "plan-1",
    title: "晚上散步",
    description: "",
    category: "life",
    due_at: null,
    status: "completed",
  });

  assert.equal(view.meta, "生活 · 不提醒");
  assert.equal(view.time, "待定");
  assert.equal(view.done, true);
  assert.equal(view.dueAt, null);
});

test("keeps profile labels and empty time formatting explicit", () => {
  assert.equal(profileLabels.high_quality_16gb, "16GB 高质量档");
  assert.equal(formatClock(null), "待定");
});

test("formats desktop calendar labels without a fake fixed date", () => {
  const date = new Date(2026, 6, 29, 20, 30);
  assert.equal(formatCalendarDate(date), "7月29日 周三");
  assert.equal(formatShortDate(date), "7月29日");
});

test("maps stored conversation messages into dialogue rows", () => {
  const createdAt = "2026-07-29T12:30:00.000Z";
  assert.deepEqual(
    toMessageView({
      id: "message-1",
      role: "assistant",
      content: "欢迎回来",
      created_at: createdAt,
      metadata: { provider: "local-model" },
    }),
    {
      id: "message-1",
      role: "agent",
      text: "欢迎回来",
      time: formatClock(createdAt),
      memory: "本地回复 · local-model",
    },
  );
});

test("formats non-empty conversation timestamps", () => {
  assert.match(
    formatConversationTime("2026-07-20T12:30:00.000Z"),
    /7月20日/,
  );
});
