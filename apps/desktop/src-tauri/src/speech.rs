//! Native macOS voice: listening (speech-to-text) and speaking (text-to-speech) for the Chief of
//! Staff, so the assistant works the same in Tauri's WKWebView as it would with real browser APIs
//! (which WKWebView does not expose: no `webkitSpeechRecognition`, and the mic/speech TCC prompts
//! need the Info.plist usage-description keys this app now ships).
//!
//! Listening spawns `native/stt_helper.swift` (see that file for why it's Swift, not a new
//! `objc2-speech`/`objc2-av-foundation` dependency tree) and streams its stdout as
//! `stt://partial` / `stt://final` / `stt://error` events. Speaking shells out to macOS's own
//! `say` (NSSpeechSynthesizer under the hood) — an already-installed native tool, so no Rust
//! speech-framework bindings are needed there either — and emits `tts://start` / `tts://end` so
//! the avatar can animate its mouth while talking, plus supports being killed mid-utterance for
//! barge-in.

use serde::Serialize;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Default)]
pub struct SpeechState {
    stt: Mutex<Option<Child>>,
    tts: Mutex<Option<Child>>,
}

#[derive(Serialize, Clone)]
struct SttEvent<'a> {
    text: &'a str,
}

fn kill(child: &mut Child) {
    // SAFETY: signalling a child process we spawned.
    unsafe {
        libc::kill(child.id() as i32, libc::SIGTERM);
    }
}

/// Starts listening. A no-op (not an error) if already listening. Emits `stt://error` and does
/// not start anything when the helper binary is missing (debug builds not yet compiled, or a
/// platform where `build.rs` skipped it) rather than silently pretending to listen.
#[tauri::command]
pub fn stt_start(app: AppHandle, state: tauri::State<SpeechState>) -> Result<(), String> {
    let mut guard = state.stt.lock().map_err(|_| "speech state poisoned")?;
    if guard.is_some() {
        return Ok(());
    }
    let helper = option_env!("STT_HELPER_PATH");
    let helper = match helper {
        Some(path) if !path.is_empty() => path,
        _ => {
            let _ = app.emit("stt://error", SttEvent { text: "Listening isn't available in this build." });
            return Ok(());
        }
    };
    let mut child = Command::new(helper)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("spawn stt helper: {e}"))?;
    let stdout = child.stdout.take().ok_or("stt helper stdout unavailable")?;
    *guard = Some(child);
    drop(guard);

    let app_for_thread = app.clone();
    std::thread::spawn(move || {
        use std::io::{BufRead, BufReader};
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            let Ok(value) = serde_json::from_str::<serde_json::Value>(&line) else { continue };
            let text = value["text"].as_str().unwrap_or("").to_string();
            match value["type"].as_str() {
                Some("partial") => {
                    let _ = app_for_thread.emit("stt://partial", SttEvent { text: &text });
                }
                Some("final") => {
                    let _ = app_for_thread.emit("stt://final", SttEvent { text: &text });
                }
                Some("error") => {
                    let _ = app_for_thread.emit("stt://error", SttEvent { text: &text });
                }
                _ => {}
            }
        }
        if let Some(state) = app_for_thread.try_state::<SpeechState>() {
            if let Ok(mut guard) = state.stt.lock() {
                *guard = None;
            }
        }
    });
    Ok(())
}

/// Stops listening. `SIGTERM` lets the helper end the audio cleanly so a trailing `stt://final`
/// (or `stt://error`, e.g. nothing was said) still arrives before it exits.
#[tauri::command]
pub fn stt_stop(state: tauri::State<SpeechState>) -> Result<(), String> {
    let mut guard = state.stt.lock().map_err(|_| "speech state poisoned")?;
    if let Some(child) = guard.as_mut() {
        kill(child);
    }
    Ok(())
}

/// Speaks `text` aloud, replacing anything currently speaking (so a new reply, or the person
/// starting to talk again, always wins — barge-in). Emits `tts://start` immediately and
/// `tts://end` once speech finishes or is stopped.
#[tauri::command]
pub fn tts_speak(app: AppHandle, state: tauri::State<SpeechState>, text: String) -> Result<(), String> {
    stop_speaking(&state)?;
    if text.trim().is_empty() {
        return Ok(());
    }
    let child = Command::new("/usr/bin/say")
        .arg(&text)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("spawn say: {e}"))?;
    let _ = app.emit("tts://start", ());
    let waited = app.clone();
    // `say`'s own child handle is moved into the waiter thread; `state.tts` below only needs to
    // let `tts_stop`/barge-in kill *this* utterance, not join on it.
    let pid = child.id();
    *state.tts.lock().map_err(|_| "speech state poisoned")? = Some(child);
    std::thread::spawn(move || {
        // Poll rather than `child.wait()` here: the `Child` handle itself lives in `state.tts`
        // (so `tts_stop` can kill it), and a `Child` cannot be waited from two places at once.
        loop {
            std::thread::sleep(std::time::Duration::from_millis(80));
            // SAFETY: WNOHANG status check of a process we spawned; reaps it once it exits so it
            // does not linger as a zombie.
            let mut status: i32 = 0;
            let ret = unsafe { libc::waitpid(pid as i32, &mut status, libc::WNOHANG) };
            if ret != 0 {
                break;
            }
        }
        let _ = waited.emit("tts://end", ());
        if let Some(state) = waited.try_state::<SpeechState>() {
            if let Ok(mut guard) = state.tts.lock() {
                *guard = None;
            }
        }
    });
    Ok(())
}

fn stop_speaking(state: &tauri::State<SpeechState>) -> Result<(), String> {
    let mut guard = state.tts.lock().map_err(|_| "speech state poisoned")?;
    if let Some(child) = guard.as_mut() {
        kill(child);
    }
    Ok(())
}

/// Stops speaking now (barge-in: the person started talking, or Settings turned replies off
/// mid-utterance). The waiter thread from `tts_speak` still emits `tts://end`.
#[tauri::command]
pub fn tts_stop(state: tauri::State<SpeechState>) -> Result<(), String> {
    stop_speaking(&state)
}
