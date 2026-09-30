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
use std::sync::{Arc, Condvar, Mutex, OnceLock};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{
    AppHandle, LogicalSize, Manager, PhysicalPosition, RunEvent, State, WebviewUrl,
    WebviewWindow, WebviewWindowBuilder, WindowEvent,
};

#[cfg(target_os = "macos")]
mod ptt;
#[cfg(target_os = "macos")]
mod speech;

const READY_PREFIX: &str = "ALPHA_CORE_READY ";
/// Generated-UI qualification fixture, served from its own origin (`alpha-ui://<app-id>/`) so
/// the shell's CSP is not inherited (srcdoc/blob documents inherit it) and the document gets
/// its own strict policy as a response header. Built by apps/desktop/scripts/build-fixture.mjs.
const FIXTURE_HTML: &[u8] = include_bytes!("../../src/qualification/generated-ui.html");
const FIXTURE_CSP: &str = include_str!("../../src/qualification/generated-ui.csp");
const ERROR_PREFIX: &str = "ALPHA_CORE_ERROR ";
/// Core's data directory, fixed once Core launches. Generated App screens are served from the
/// sealed Versions inside it.
static DATA_DIR: OnceLock<PathBuf> = OnceLock::new();
/// `<data dir>/logs/host.log`: what the host did and why Core did or did not start. A Mac app
/// launched from the Finder has no terminal, so stderr alone would lose these lines.
static HOST_LOG: OnceLock<PathBuf> = OnceLock::new();
const READY_TIMEOUT: Duration = Duration::from_secs(60);

fn note(message: &str) {
    eprintln!("[host] {message}");
    if let Some(path) = HOST_LOG.get() {
        use std::io::Write;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
            let _ = writeln!(file, "{stamp} {message}");
        }
    }
}
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

/// The Core launch outcome, shared between the launch thread and the shell's commands. Core
/// starts off the main thread so the window appears at once; a first launch from the Finder
/// may sit in a macOS folder-access prompt for as long as the person takes to answer it.
#[derive(Default)]
struct Launch {
    core: Mutex<Option<CoreProcess>>,
    launch_error: Mutex<Option<String>>,
    settled: (Mutex<bool>, Condvar),
}

impl Launch {
    fn settle(&self, outcome: Result<CoreProcess, String>) {
        match outcome {
            Ok(core) => *self.core.lock().unwrap() = Some(core),
            Err(error) => *self.launch_error.lock().unwrap() = Some(error),
        }
        let (done, ready) = &self.settled;
        *done.lock().unwrap() = true;
        ready.notify_all();
    }

    /// Block until the launch settled, or `timeout` passed.
    fn wait(&self, timeout: Duration) -> bool {
        let (done, ready) = &self.settled;
        let guard = done.lock().unwrap();
        let (guard, _) = ready
            .wait_timeout_while(guard, timeout, |settled| !*settled)
            .unwrap();
        *guard
    }
}

#[derive(Default)]
struct HostState {
    launch: Arc<Launch>,
}

/// How long the shell waits for Core before it is told the runtime did not start.
const SESSION_WAIT: Duration = Duration::from_secs(600);

/// The desktop assistant: a small always-on-top window with Alpha's character that the person
/// talks to from anywhere (run, read, open, change or build, at once). Its own webview loads
/// the same shell, which renders the avatar when the window label says so.
const AVATAR_LABEL: &str = "avatar";
const AVATAR_IDLE: (f64, f64) = (132.0, 148.0);
const AVATAR_OPEN: (f64, f64) = (380.0, 560.0);
const AVATAR_MARGIN: f64 = 20.0;
/// Present in the data directory when the person hid the avatar; it stays hidden until shown.
const AVATAR_HIDDEN_MARKER: &str = "avatar-hidden";

fn avatar_marker() -> Option<PathBuf> {
    DATA_DIR.get().map(|d| d.join(AVATAR_HIDDEN_MARKER))
}

fn place_bottom_right(window: &WebviewWindow, size: (f64, f64)) -> tauri::Result<()> {
    let monitor = match window.current_monitor()? {
        Some(m) => Some(m),
        None => window.primary_monitor()?,
    };
    if let Some(monitor) = monitor {
        let scale = monitor.scale_factor();
        let area = monitor.work_area();
        let x = area.position.x as f64 + area.size.width as f64 - (size.0 + AVATAR_MARGIN) * scale;
        let y = area.position.y as f64 + area.size.height as f64 - (size.1 + AVATAR_MARGIN) * scale;
        window.set_position(PhysicalPosition::new(x.round() as i32, y.round() as i32))?;
    }
    Ok(())
}

fn build_avatar(app: &AppHandle) -> tauri::Result<()> {
    let window = WebviewWindowBuilder::new(app, AVATAR_LABEL, WebviewUrl::App("index.html".into()))
        .title("Alpha assistant")
        .inner_size(AVATAR_IDLE.0, AVATAR_IDLE.1)
        .resizable(false)
        .decorations(false)
        .transparent(true)
        .shadow(false)
        .always_on_top(true)
        .visible_on_all_workspaces(true)
        .skip_taskbar(true)
        .focused(false)
        .visible(false)
        .build()?;
    place_bottom_right(&window, AVATAR_IDLE)?;
    let hidden = avatar_marker().map(|m| m.exists()).unwrap_or(false);
    if !hidden {
        window.show()?;
    }
    Ok(())
}

/// Grow the avatar into its panel (or back), keeping its bottom-right corner where it is, so
/// it opens upward and leftward from wherever the person left it.
#[tauri::command]
fn avatar_layout(app: AppHandle, expanded: bool) -> Result<(), String> {
    let window = app
        .get_webview_window(AVATAR_LABEL)
        .ok_or("no avatar window")?;
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let position = window.outer_position().map_err(|e| e.to_string())?;
    let size = window.outer_size().map_err(|e| e.to_string())?;
    let right = position.x + size.width as i32;
    let bottom = position.y + size.height as i32;
    let (width, height) = if expanded { AVATAR_OPEN } else { AVATAR_IDLE };
    window
        .set_size(LogicalSize::new(width, height))
        .map_err(|e| e.to_string())?;
    let physical_w = (width * scale).round() as i32;
    let physical_h = (height * scale).round() as i32;
    window
        .set_position(PhysicalPosition::new(right - physical_w, bottom - physical_h))
        .map_err(|e| e.to_string())?;
    if expanded {
        let _ = window.set_focus();
    }
    Ok(())
}

#[tauri::command]
fn avatar_visible(app: AppHandle, visible: bool) -> Result<bool, String> {
    let window = app
        .get_webview_window(AVATAR_LABEL)
        .ok_or("no avatar window")?;
    if visible {
        window.show().map_err(|e| e.to_string())?;
        if let Some(marker) = avatar_marker() {
            let _ = std::fs::remove_file(marker);
        }
    } else {
        window.hide().map_err(|e| e.to_string())?;
        if let Some(marker) = avatar_marker() {
            let _ = std::fs::write(marker, b"");
        }
    }
    Ok(visible)
}

#[tauri::command]
fn avatar_is_visible(app: AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window(AVATAR_LABEL)
        .ok_or("no avatar window")?;
    window.is_visible().map_err(|e| e.to_string())
}

/// Bring the main window forward (the avatar hands a module or conversation over to it).
#[tauri::command]
fn show_main(app: AppHandle) -> Result<(), String> {
    show_main_window(&app);
    Ok(())
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

/// Platform resources (App template, builder references, UI build tool, render check). In
/// development this is the repository root; F22 replaces it with the bundled resources.
fn platform_resources() -> PathBuf {
    if let Ok(dir) = std::env::var("ALPHA_PLATFORM_RESOURCES") {
        return PathBuf::from(dir);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

/// The pinned Node 24 the UI build profile was made with (Homebrew keg in development).
fn pinned_node() -> Option<PathBuf> {
    let keg = PathBuf::from("/opt/homebrew/opt/node@24/bin/node");
    keg.is_file().then_some(keg)
}

/// The headless browser Playwright 1.62.0 pins for the render check (F07 decision §4).
fn validator_browser(home: &str) -> Option<PathBuf> {
    let exe = PathBuf::from(home).join(
        "Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell",
    );
    exe.is_file().then_some(exe)
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
    let mut data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app data dir: {e}"))?;
    if cfg!(debug_assertions) {
        // Development/qualification only: run a second instance on its own data directory.
        if let Ok(dir) = std::env::var("ALPHA_DATA_DIR") {
            if !dir.is_empty() {
                data_dir = PathBuf::from(dir);
            }
        }
    }
    std::fs::create_dir_all(&data_dir).map_err(|e| format!("create data dir: {e}"))?;
    let _ = DATA_DIR.set(data_dir.clone());
    let token = random_token()?;
    let log_dir = data_dir.join("logs");
    std::fs::create_dir_all(&log_dir).map_err(|e| format!("create log dir: {e}"))?;
    let _ = HOST_LOG.set(log_dir.join("host.log"));
    note(&format!(
        "launching core: python={} runtime={} resources={} data={}",
        python.display(),
        runtime.display(),
        platform_resources().display(),
        data_dir.display()
    ));
    let core_log = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("core.stderr.log"))
        .map_err(|e| format!("open core log: {e}"))?;
    let allowed_origins = if cfg!(debug_assertions) {
        "http://localhost:1420,tauri://localhost"
    } else {
        "tauri://localhost"
    };

    // Builder toolchain (founder decision 2026-09-25): the Claude Code CLI route runs from the
    // user's own login, so the builder profile gets the user's HOME and a fixed toolchain PATH.
    let user_home = std::env::var("HOME").unwrap_or_default();
    let builder_path = "/opt/homebrew/bin:/opt/homebrew/opt/node@24/bin:/usr/local/bin:/usr/bin:/bin";
    let mut command = Command::new(&python);
    command
        .args(["-I", "-m", "alpha.main"])
        .env_clear()
        // Enabling a route only allows it to be chosen in Settings -> Models; it costs nothing
        // until the person actually connects an account/key and picks it as the provider.
        .env(
            "ALPHA_ENABLED_MODEL_ROUTES",
            "fake,claude-code-cli,chatgpt-codex-cli,chatgpt-api,openrouter,grok",
        )
        .env("ALPHA_BUILDER_PATH", builder_path)
        .env("ALPHA_BUILDER_HOME", &user_home)
        .env("ALPHA_DATA_DIR", &data_dir)
        // Published App runtime profiles (`just bundle-core`); Core verifies, never installs.
        .env("ALPHA_PROFILES_DIR", runtime.join("profiles"))
        // Build pipeline (F07/F08): templates, the UI build tool and render check, the pinned
        // Node and headless browser. Development locations; F22 bundles them as resources.
        .env("ALPHA_PLATFORM_RESOURCES", platform_resources())
        .env("ALPHA_SESSION_TOKEN", &token)
        .env("ALPHA_ALLOWED_ORIGINS", allowed_origins)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("LC_ALL", "C.UTF-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(core_log));
    if let Some(node) = pinned_node() {
        command.env("ALPHA_NODE", node);
    }
    if let Some(browser) = validator_browser(&user_home) {
        command.env("ALPHA_UI_BROWSER", browser);
    }
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
            return Err(format!(
                "core did not report readiness within {}s",
                READY_TIMEOUT.as_secs()
            ));
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
                note(&format!("core exited: {status}"));
                return;
            }
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(50)),
            _ => break,
        }
    }
    note("core did not stop within grace; killing");
    let _ = process.child.kill();
    let _ = process.child.wait();
}

#[tauri::command]
async fn core_session(state: State<'_, HostState>) -> Result<CoreSession, String> {
    let launch = state.launch.clone();
    tauri::async_runtime::spawn_blocking(move || {
        if !launch.wait(SESSION_WAIT) {
            return Err(
                "Alpha's runtime is still starting. If macOS is asking whether Alpha may \
                 access a folder, allow it and reopen Alpha."
                    .to_string(),
            );
        }
        let guard = launch.core.lock().map_err(|_| "host state poisoned")?;
        match guard.as_ref() {
            Some(core) => Ok(CoreSession {
                base_url: format!("http://127.0.0.1:{}", core.info.core_port),
                token: core.token.clone(),
            }),
            None => Err(launch
                .launch_error
                .lock()
                .ok()
                .and_then(|e| e.clone())
                .unwrap_or_else(|| "core not running".into())),
        }
    })
    .await
    .map_err(|e| format!("host task failed: {e}"))?
}

#[tauri::command]
fn runtime_info(state: State<'_, HostState>) -> Result<RuntimeInfo, String> {
    let guard = state.launch.core.lock().map_err(|_| "host state poisoned")?;
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
        if let Ok(mut guard) = state.launch.core.lock() {
            if let Some(mut core) = guard.take() {
                stop_core(&mut core);
            }
        }
    }
    app.exit(0);
}

fn generated_ui_response(request: &tauri::http::Request<Vec<u8>>) -> tauri::http::Response<Vec<u8>> {
    let path = request.uri().path();
    let host = request.uri().host().unwrap_or("");
    // F03 qualification fixture (development builds only).
    if cfg!(debug_assertions)
        && (host == "fixture_a" || host == "fixture_b")
        && (path == "/" || path == "/index.html")
    {
        return html_response(FIXTURE_HTML.to_vec(), FIXTURE_CSP.trim());
    }
    // A generated App's screen: alpha-ui://<app_id>/<version_id>/index.html. The host part is
    // the App identity (its own origin); the sealed Version must belong to that App.
    match app_screen(host, path) {
        Some((html, csp)) => html_response(html, &csp),
        None => tauri::http::Response::builder()
            .status(404)
            .header("Content-Type", "text/plain")
            .body(b"not found".to_vec())
            .expect("response"),
    }
}

fn html_response(body: Vec<u8>, csp: &str) -> tauri::http::Response<Vec<u8>> {
    tauri::http::Response::builder()
        .status(200)
        .header("Content-Type", "text/html; charset=utf-8")
        .header("Content-Security-Policy", csp)
        .header("Cache-Control", "no-store")
        .header("X-Content-Type-Options", "nosniff")
        .body(body)
        .expect("response")
}

fn valid_id(value: &str, prefix: &str, max: usize) -> bool {
    value.starts_with(prefix)
        && value.len() <= max
        && value
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '_')
}

/// The sealed screen of `version_id`, if that Version belongs to App `app_id` and has one.
fn app_screen(app_id: &str, path: &str) -> Option<(Vec<u8>, String)> {
    let mut parts = path.trim_start_matches('/').splitn(2, '/');
    let version_id = parts.next()?;
    if parts.next()? != "index.html" || !valid_id(version_id, "ver_", 40) || !valid_id(app_id, "", 64) {
        return None;
    }
    let version = DATA_DIR.get()?.join("versions").join(version_id);
    let index: serde_json::Value =
        serde_json::from_slice(&std::fs::read(version.join("package.index.json")).ok()?).ok()?;
    if index["app_id"].as_str()? != app_id {
        return None;
    }
    let html = std::fs::read(version.join("dist/ui/index.html")).ok()?;
    let csp = std::fs::read_to_string(version.join("dist/ui/index.csp")).ok()?;
    Some((html, csp.trim().to_string()))
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(HostState::default())
        .manage(ptt::PttState::default())
        .manage(speech::SpeechState::default())
        .register_uri_scheme_protocol("alpha-ui", |_ctx, request| generated_ui_response(&request))
        .invoke_handler(tauri::generate_handler![
            core_session,
            runtime_info,
            avatar_layout,
            avatar_visible,
            avatar_is_visible,
            show_main,
            ptt::ptt_permission,
            ptt::ptt_request_permission,
            ptt::ptt_set_shortcut,
            speech::stt_start,
            speech::stt_stop,
            speech::tts_speak,
            speech::tts_stop
        ])
        .setup(|app| {
            ptt::start(app.handle().clone(), app.state::<ptt::PttState>().inner());
            let handle = app.handle().clone();
            let launch = app.state::<HostState>().launch.clone();
            std::thread::Builder::new()
                .name("core-launch".into())
                .spawn(move || {
                    let outcome = launch_core(&handle);
                    match &outcome {
                        Ok(core) => note(&format!(
                            "core pid {} on port {} ({})",
                            core.info.core_pid, core.info.core_port, core.info.python_executable
                        )),
                        Err(error) => note(&format!("core launch failed: {error}")),
                    }
                    launch.settle(outcome);
                })
                .expect("core launch thread");

            #[cfg(debug_assertions)]
            if std::env::var("ALPHA_OPEN_DEVTOOLS").as_deref() == Ok("1") {
                if let Some(window) = app.get_webview_window("main") {
                    window.open_devtools();
                }
            }

            if let Err(error) = build_avatar(app.handle()) {
                note(&format!("avatar window not created: {error}"));
            }

            let open = MenuItem::with_id(app, "open", "Open Alpha", true, None::<&str>)?;
            let avatar_item =
                MenuItem::with_id(app, "avatar", "Show or hide the assistant", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit Alpha", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &avatar_item, &quit_item])?;
            // A dedicated monochrome silhouette, not the app icon: macOS templates recolor a
            // flat black-on-transparent shape to match the menu bar's light/dark state, and
            // the full-color panda (rendered fully opaque) reads as a solid dark blob there.
            let tray_icon = tauri::include_image!("icons/tray@2x.png");
            TrayIconBuilder::with_id("main")
                .icon(tray_icon)
                .icon_as_template(true)
                .tooltip("Alpha runtime is running")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "open" => show_main_window(app),
                    "avatar" => {
                        let shown = avatar_is_visible(app.clone()).unwrap_or(false);
                        let _ = avatar_visible(app.clone(), !shown);
                    }
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
                    if let Ok(mut guard) = state.launch.core.lock() {
                        if let Some(mut core) = guard.take() {
                            stop_core(&mut core);
                        }
                    }
                }
            }
            _ => {}
        });
}
