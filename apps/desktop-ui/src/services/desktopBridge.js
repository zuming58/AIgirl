export function isDesktopRuntime() {
  return Boolean(globalThis.window?.__TAURI_INTERNALS__);
}

async function withCurrentWindow(action) {
  if (!isDesktopRuntime()) return false;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await action(getCurrentWindow());
  return true;
}

export function createDesktopBridge({
  now = () => Date.now(),
  notificationDedupeMs = 60_000,
} = {}) {
  const recentNotifications = new Map();

  async function notify(title, body) {
    const key = `${title}\u0000${body}`;
    const current = now();
    const previous = recentNotifications.get(key);
    if (previous !== undefined && current - previous < notificationDedupeMs) {
      return false;
    }

    let delivered = false;
    if (isDesktopRuntime()) {
      const { isPermissionGranted, sendNotification } = await import(
        "@tauri-apps/plugin-notification"
      );
      if (!(await isPermissionGranted())) return false;
      sendNotification({ title, body });
      delivered = true;
    } else if (
      "Notification" in globalThis.window &&
      globalThis.window.Notification.permission === "granted"
    ) {
      new globalThis.window.Notification(title, { body });
      delivered = true;
    }

    if (delivered) {
      recentNotifications.set(key, current);
      for (const [candidate, deliveredAt] of recentNotifications) {
        if (current - deliveredAt >= notificationDedupeMs) {
          recentNotifications.delete(candidate);
        }
      }
    }
    return delivered;
  }

  return {
    minimize: () => withCurrentWindow((window) => window.minimize()),
    toggleMaximize: () =>
      withCurrentWindow((window) => window.toggleMaximize()),
    close: () => withCurrentWindow((window) => window.close()),
    notify,

    async isAutostartEnabled() {
      if (!isDesktopRuntime()) return false;
      const { isEnabled } = await import("@tauri-apps/plugin-autostart");
      return isEnabled();
    },

    async setAutostart(enabled) {
      if (!isDesktopRuntime()) return false;
      const { enable, disable } = await import("@tauri-apps/plugin-autostart");
      await (enabled ? enable() : disable());
      return true;
    },
  };
}

export const desktopBridge = createDesktopBridge();
