use std::{
  net::{SocketAddr, TcpStream},
  sync::Mutex,
  time::Duration,
};
use tauri::{
  menu::{Menu, MenuItem},
  tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
  Manager, RunEvent, WindowEvent,
};
use tauri_plugin_shell::{
  process::{CommandChild, CommandEvent},
  ShellExt,
};

struct CoreSidecar(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let app = tauri::Builder::default()
    .plugin(tauri_plugin_notification::init())
    .plugin(tauri_plugin_shell::init())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
          .build(),
        )?;
      }

      #[cfg(desktop)]
      app.handle().plugin(tauri_plugin_autostart::init(
        tauri_plugin_autostart::MacosLauncher::LaunchAgent,
        None,
      ))?;

      let core_child = start_core_sidecar(app);
      app.manage(CoreSidecar(Mutex::new(core_child)));

      let show = MenuItem::with_id(app, "show", "显示心屿", true, None::<&str>)?;
      let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
      let menu = Menu::with_items(app, &[&show, &quit])?;
      TrayIconBuilder::new()
        .icon(app.default_window_icon().expect("application icon").clone())
        .tooltip("心屿 XINYU")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
          "show" => show_main_window(app),
          "quit" => {
            stop_core_sidecar(app);
            app.exit(0);
          }
          _ => {}
        })
        .on_tray_icon_event(|tray, event| {
          if let TrayIconEvent::Click {
            button: MouseButton::Left,
            button_state: MouseButtonState::Up,
            ..
          } = event
          {
            show_main_window(tray.app_handle());
          }
        })
        .build(app)?;
      Ok(())
    })
    .on_window_event(|window, event| {
      if let WindowEvent::CloseRequested { api, .. } = event {
        api.prevent_close();
        let _ = window.hide();
      }
    })
    .build(tauri::generate_context!())
    .expect("error while building tauri application");

  app.run(|app, event| {
    if let RunEvent::Exit = event {
      stop_core_sidecar(app);
    }
  });
}

fn show_main_window(app: &tauri::AppHandle) {
  if let Some(window) = app.get_webview_window("main") {
    let _ = window.unminimize();
    let _ = window.show();
    let _ = window.set_focus();
  }
}

fn start_core_sidecar(app: &tauri::App) -> Option<CommandChild> {
  let address = SocketAddr::from(([127, 0, 0, 1], 8765));
  if TcpStream::connect_timeout(&address, Duration::from_millis(180)).is_ok() {
    log::info!("Xinyu Core already listens on 127.0.0.1:8765");
    return None;
  }

  let parent_pid = std::process::id().to_string();
  let command = match app.shell().sidecar("xinyu-core") {
    Ok(command) => command.args([
      "--host",
      "127.0.0.1",
      "--port",
      "8765",
      "--parent-pid",
      parent_pid.as_str(),
    ]),
    Err(error) => {
      log::error!("Unable to prepare Xinyu Core sidecar: {error}");
      return None;
    }
  };

  match command.spawn() {
    Ok((mut receiver, child)) => {
      tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
          match event {
            CommandEvent::Stdout(bytes) => {
              log::info!("core: {}", String::from_utf8_lossy(&bytes));
            }
            CommandEvent::Stderr(bytes) => {
              log::warn!("core: {}", String::from_utf8_lossy(&bytes));
            }
            CommandEvent::Terminated(payload) => {
              log::info!("Xinyu Core exited: {payload:?}");
            }
            _ => {}
          }
        }
      });
      Some(child)
    }
    Err(error) => {
      log::error!("Unable to start Xinyu Core sidecar: {error}");
      None
    }
  }
}

fn stop_core_sidecar(app: &tauri::AppHandle) {
  if let Some(state) = app.try_state::<CoreSidecar>() {
    if let Ok(mut guard) = state.0.lock() {
      if let Some(mut child) = guard.take() {
        let _ = child.kill();
      }
    }
  }
}
