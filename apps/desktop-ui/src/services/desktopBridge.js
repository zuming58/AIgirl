export function isDesktopRuntime() {
  return Boolean(globalThis.window?.__TAURI_INTERNALS__);
}

async function withCurrentWindow(action) {
  if (!isDesktopRuntime()) return false;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await action(getCurrentWindow());
  return true;
}

export const desktopBridge = {
  minimize: () => withCurrentWindow((window) => window.minimize()),
  toggleMaximize: () =>
    withCurrentWindow((window) => window.toggleMaximize()),
  close: () => withCurrentWindow((window) => window.close()),

  async notify(title, body) {
    if (isDesktopRuntime()) {
      const { isPermissionGranted, sendNotification } = await import(
        "@tauri-apps/plugin-notification"
      );
      if (!(await isPermissionGranted())) return false;
      sendNotification({ title, body });
      return true;
    }
    if (
      "Notification" in globalThis.window &&
      globalThis.window.Notification.permission === "granted"
    ) {
      new globalThis.window.Notification(title, { body });
      return true;
    }
    return false;
  },

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
