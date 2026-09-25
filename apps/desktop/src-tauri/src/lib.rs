//! Alpha native host.
//!
//! Responsibilities (System Architecture, "Native host"): window/tray lifecycle and supervised
//! Core process control. It launches the registered Core runtime with an allowlisted
//! environment and a random session credential, hands that credential to the trusted shell
//! through one typed command, keeps the runtime alive when the window closes, and terminates
//! the Core process tree on explicit quit.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager, RunEvent, State, WindowEvent};

const READY_PREFIX: &str = "ALPHA_CORE_READY ";
const ERROR_PREFIX: &str = "ALPHA_CORE_ERROR ";
const READY_TIMEOUT: Duration = Duration::from_secs(30);
const QUIT_GRACE: Duration = Duration::from_secs(5);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CoreSession {
    base_url: String,
    token: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeInfo {
    core_pid: u32,
    core_port: u16,
    core_instance_id: String,
    python_executable: String,
    runtime_dir: String,
    data_dir: String,
    core_version: String,
}

struct CoreProcess {
    child: Child,
    info: RuntimeInfo,
    token: String,
}

#[derive(Default)]
struct HostState {
    core: Mutex<Option<CoreProcess>>,
    launch_error: Mutex<Option<String>>,
}

fn random_token() -> Result<String, String> {
    use std::io::Read;
    let mut file = std::fs::File::open("/dev/urandom").map_err(|e| format!("urandom: {e}"))?;
    let mut buf = [0u8; 32];
    file.read_exact(&mut buf).map_err(|e| format!("urandom: {e}"))?;
    Ok(buf.iter().map(|b| format!("{b:02x}")).collect())
}

/// The platform-managed Core runtime directory. In development it is `<repo>/.alpha-runtime`
/// (created by `just bundle-core`); `ALPHA_RUNTIME_DIR` overrides it. F22 replaces this with a
/// signed resource bundle. The user's own Python installations are never consulted.
fn runtime_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("ALPHA_RUNTIME_DIR") {
        return PathBuf::from(dir);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../.alpha-runtime")
}

fn launch_core(app: &AppHandle) -> Result<CoreProcess, String> {
    let runtime = runtime_dir();
    let manifest_path = runtime.join("core-runtime.json");
    let manifest: serde_json::Value = serde_json::from_slice(
        &std::fs::read(&manifest_path)
            .map_err(|e| format!("Core runtime not prepared ({}): {e}. Run `just bundle-core`.", manifest_path.display()))?,
    )
    .map_err(|e| format!("invalid core-runtime.json: {e}"))?;
    let python = runtime.join(
        manifest["python"]
            .as_str()
            .ok_or("core-runtime.json missing python")?,
    );
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app data dir: {e}"))?;
    std::fs::create_dir_all(&data_dir).map_err(|e| format!("create data dir: {e}"))?;
    let token = random_token()?;
    let allowed_origins = if cfg!(debug_assertions) {
        "http://localhost:1420,tauri://localhost"
    } else {
        "tauri://localhost"
    };

    let mut command = Command::new(&python);
    command
        .args(["-I", "-m", "alpha.main"])
        .env_clear()
        .env("ALPHA_DATA_DIR", &data_dir)
        .env("ALPHA_SESSION_TOKEN", &token)
        .env("ALPHA_ALLOWED_ORIGINS", allowed_origins)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("LC_ALL", "C.UTF-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    if cfg!(debug_assertions) {
        // Development diagnostics only: forward an explicit request-logging switch.
        if let Ok(value) = std::env::var("ALPHA_LOG_REQUESTS") {
            command.env("ALPHA_LOG_REQUESTS", value);
        }
    }
    let mut child = command
        .spawn()
        .map_err(|e| format!("spawn core ({}): {e}", python.display()))?;

    let stdout = child.stdout.take().ok_or("core stdout unavailable")?;
    let mut reader = BufReader::new(stdout);
    let started = Instant::now();
    let ready_line = loop {
        if started.elapsed() > READY_TIMEOUT {
            let _ = child.kill();
            return Err("core did not report readiness in time".into());
        }
        let mut line = String::new();
        let n = reader.read_line(&mut line).map_err(|e| format!("read core stdout: {e}"))?;
        if n == 0 {
            let status = child.wait().map(|s| s.to_string()).unwrap_or_default();
            return Err(format!("core exited before readiness ({status})"));
        }
        if let Some(rest) = line.strip_prefix(ERROR_PREFIX) {
            let _ = child.kill();
            return Err(format!("core refused to start: {}", rest.trim()));
        }
        if let Some(rest) = line.strip_prefix(READY_PREFIX) {
            break rest.trim().to_string();
        }
    };
    // Keep draining stdout so the child never blocks on a full pipe.
    std::thread::spawn(move || {
        for line in reader.lines().map_while(Result::ok) {
            eprintln!("[core] {line}");
        }
    });
    let ready: serde_json::Value =
        serde_json::from_str(&ready_line).map_err(|e| format!("bad ready line: {e}"))?;
    let port = ready["port"].as_u64().ok_or("ready line missing port")? as u16;
    let info = RuntimeInfo {
        core_pid: child.id(),
        core_port: port,
        core_instance_id: ready["core_instance_id"].as_str().unwrap_or("").to_string(),
        python_executable: ready["python_executable"].as_str().unwrap_or("").to_string(),
        runtime_dir: runtime.to_string_lossy().into_owned(),
        data_dir: data_dir.to_string_lossy().into_owned(),
        core_version: ready["core_version"].as_str().unwrap_or("").to_string(),
    };
    Ok(CoreProcess { child, info, token })
}

/// Explicit quit: SIGTERM the Core (it terminates its worker trees and marks runs interrupted),
/// wait up to the grace period, then SIGKILL.
fn stop_core(process: &mut CoreProcess) {
    let pid = process.child.id() as i32;
    // SAFETY: signalling a child process we spawned.
    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }
    let deadline = Instant::now() + QUIT_GRACE;
    loop {
        match process.child.try_wait() {
            Ok(Some(status)) => {
                eprintln!("[host] core exited: {status}");
                return;
            }
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(50)),
            _ => break,
        }
    }
    eprintln!("[host] core did not stop within grace; killing");
    let _ = process.child.kill();
    let _ = process.child.wait();
}

#[tauri::command]
fn core_session(state: State<'_, HostState>) -> Result<CoreSession, String> {
    let guard = state.core.lock().map_err(|_| "host state poisoned")?;
    match guard.as_ref() {
        Some(core) => Ok(CoreSession {
            base_url: format!("http://127.0.0.1:{}", core.info.core_port),
            token: core.token.clone(),
        }),
        None => Err(state
            .launch_error
            .lock()
            .ok()
            .and_then(|e| e.clone())
            .unwrap_or_else(|| "core not running".into())),
    }
}

#[tauri::command]
fn runtime_info(state: State<'_, HostState>) -> Result<RuntimeInfo, String> {
    let guard = state.core.lock().map_err(|_| "host state poisoned")?;
    guard
        .as_ref()
        .map(|c| c.info.clone())
        .ok_or_else(|| "core not running".into())
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn quit(app: &AppHandle) {
    if let Some(state) = app.try_state::<HostState>() {
        if let Ok(mut guard) = state.core.lock() {
            if let Some(mut core) = guard.take() {
                stop_core(&mut core);
            }
        }
    }
    app.exit(0);
}

pub fn run() {
    tauri::Builder::default()
        .manage(HostState::default())
        .invoke_handler(tauri::generate_handler![core_session, runtime_info])
        .setup(|app| {
            let handle = app.handle().clone();
            match launch_core(&handle) {
                Ok(core) => {
                    eprintln!(
                        "[host] core pid {} on port {} ({})",
                        core.info.core_pid, core.info.core_port, core.info.python_executable
                    );
                    *app.state::<HostState>().core.lock().unwrap() = Some(core);
                }
                Err(error) => {
                    eprintln!("[host] core launch failed: {error}");
                    *app.state::<HostState>().launch_error.lock().unwrap() = Some(error);
                }
            }

            #[cfg(debug_assertions)]
            if std::env::var("ALPHA_OPEN_DEVTOOLS").as_deref() == Ok("1") {
                if let Some(window) = app.get_webview_window("main") {
                    window.open_devtools();
                }
            }

            let open = MenuItem::with_id(app, "open", "Open Alpha", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit Alpha", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit_item])?;
            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().cloned().expect("window icon"))
                .icon_as_template(true)
                .tooltip("Alpha runtime is running")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "open" => show_main_window(app),
                    "quit" => quit(app),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the window preserves the runtime and tray; only explicit quit stops it.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
                eprintln!("[host] window hidden; runtime keeps running");
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Alpha")
        .run(|app, event| match event {
            #[cfg(target_os = "macos")]
            RunEvent::Reopen { .. } => show_main_window(app),
            RunEvent::ExitRequested { code: None, api, .. } => {
                // No windows left (never expected: close is intercepted). Keep the runtime.
                api.prevent_exit();
            }
            RunEvent::Exit => {
                // Cmd+Q / app menu Quit / tray Quit all end here; stop Core once.
                if let Some(state) = app.try_state::<HostState>() {
                    if let Ok(mut guard) = state.core.lock() {
                        if let Some(mut core) = guard.take() {
                            stop_core(&mut core);
                        }
                    }
                }
            }
            _ => {}
        });
}
