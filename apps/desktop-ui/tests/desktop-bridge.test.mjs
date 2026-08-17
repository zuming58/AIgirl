import assert from "node:assert/strict";
import test from "node:test";

import { createDesktopBridge } from "../src/services/desktopBridge.js";

test("browser notification adapter deduplicates reconnect deliveries", async () => {
  const delivered = [];
  let clock = 1_000;
  class MockNotification {
    static permission = "granted";

    constructor(title, options) {
      delivered.push({ title, body: options.body });
    }
  }
  globalThis.window = { Notification: MockNotification };
  const bridge = createDesktopBridge({
    now: () => clock,
    notificationDedupeMs: 60_000,
  });

  assert.equal(await bridge.notify("心屿 · 计划提醒", "准备开会"), true);
  assert.equal(await bridge.notify("心屿 · 计划提醒", "准备开会"), false);
  clock += 60_000;
  assert.equal(await bridge.notify("心屿 · 计划提醒", "准备开会"), true);
  assert.equal(delivered.length, 2);
});

test("notification adapter does not deduplicate denied deliveries", async () => {
  class MockNotification {
    static permission = "denied";
  }
  globalThis.window = { Notification: MockNotification };
  const bridge = createDesktopBridge();

  assert.equal(await bridge.notify("提醒", "未授权"), false);
  MockNotification.permission = "granted";
  assert.equal(await bridge.notify("提醒", "未授权"), true);
});
