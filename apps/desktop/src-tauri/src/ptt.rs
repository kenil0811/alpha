//! Push-to-talk: hold a key down to start voice capture into the avatar/Chief of Staff, release
//! to stop. Fn is the default shortcut, and it is a modifier *flag*, not a key —
//! `tauri-plugin-global-shortcut` cannot register it. So this watches raw key events with a
//! macOS `CGEventTap` instead (also covers a non-Fn combo the person records, with no extra
//! dependency: `core-graphics`/`core-foundation` are already in Cargo.lock, pulled in
//! transitively by tauri/wry).
//!
//! A hold shorter than [`HOLD_MS`] fires nothing, so a quick tap of Fn still does whatever it
//! normally does (emoji picker, dictation, function-key toggle) instead of every tap starting
//! and stopping a capture.

use core_foundation::runloop::CFRunLoop;
use core_graphics::event::{
    CGEventFlags, CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement,
    CGEventType, CallbackResult, EventField,
};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Emitter};

const HOLD_MS: u64 = 300;

#[derive(Clone, Copy, Serialize, Deserialize, Debug, PartialEq)]
#[serde(tag = "mode", rename_all = "lowercase")]
pub enum PttShortcut {
    Fn,
    /// A recorded key + modifier combo. `code` is a macOS virtual keycode (`event.keyCode` in
    /// the browser lines up with it for the common letter/number/space keys the recorder offers).
    Key { code: u16, shift: bool, control: bool, alt: bool, command: bool },
}

impl Default for PttShortcut {
    fn default() -> Self {
        PttShortcut::Fn
    }
}

struct PttRuntime {
    shortcut: Mutex<PttShortcut>,
    /// Bumped on every press/release; lets a pending hold-timer notice it is stale (the key was
    /// released, or the shortcut changed, before it fired).
    generation: AtomicU64,
    held: AtomicBool,
    /// Whether `ptt://start` fired for the current hold (so release only emits `ptt://stop`
    /// when a start actually went out).
    started: AtomicBool,
}

pub struct PttState(Arc<PttRuntime>);

impl Default for PttState {
    fn default() -> Self {
        PttState(Arc::new(PttRuntime {
            shortcut: Mutex::new(PttShortcut::Fn),
            generation: AtomicU64::new(0),
            held: AtomicBool::new(false),
            started: AtomicBool::new(false),
        }))
    }
}

// Declared by hand rather than pulling in another crate: `CGPreflightListenEventAccess` /
// `CGRequestListenEventAccess` live in the CoreGraphics framework core-graphics already links.
extern "C" {
    fn CGPreflightListenEventAccess() -> bool;
    fn CGRequestListenEventAccess() -> bool;
}

/// Whether the app can already watch global key events (Input Monitoring / Accessibility). The
/// UI uses this to show an honest state instead of pretending the shortcut works.
#[tauri::command]
pub fn ptt_permission() -> bool {
    unsafe { CGPreflightListenEventAccess() }
}

/// Prompts the system permission dialog (a no-op if already granted or already denied once).
#[tauri::command]
pub fn ptt_request_permission() -> bool {
    unsafe { CGRequestListenEventAccess() }
}

#[tauri::command]
pub fn ptt_set_shortcut(state: tauri::State<PttState>, shortcut: PttShortcut) {
    *state.0.shortcut.lock().unwrap() = shortcut;
    // A shortcut change mid-hold should not leave a stuck "listening" state behind.
    state.0.held.store(false, Ordering::SeqCst);
    state.0.started.store(false, Ordering::SeqCst);
    state.0.generation.fetch_add(1, Ordering::SeqCst);
}

fn handle_edge(down: bool, rt: &Arc<PttRuntime>, app: &AppHandle) {
    let was_held = rt.held.swap(down, Ordering::SeqCst);
    if down == was_held {
        return; // autorepeat KeyDown, or a duplicate flag event; not a fresh press/release
    }
    if down {
        let generation = rt.generation.fetch_add(1, Ordering::SeqCst) + 1;
        let rt = rt.clone();
        let app = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(HOLD_MS));
            if rt.held.load(Ordering::SeqCst) && rt.generation.load(Ordering::SeqCst) == generation {
                rt.started.store(true, Ordering::SeqCst);
                let _ = app.emit("ptt://start", ());
            }
        });
    } else {
        rt.generation.fetch_add(1, Ordering::SeqCst); // invalidate any pending hold-timer
        if rt.started.swap(false, Ordering::SeqCst) {
            let _ = app.emit("ptt://stop", ());
        }
    }
}

/// Starts the background monitor thread. Runs for the life of the app; a missing permission
/// just leaves it inert (`ptt_permission` tells the UI so it can say so honestly).
pub fn start(app: AppHandle, state: &PttState) {
    let rt = state.0.clone();
    std::thread::Builder::new()
        .name("ptt-monitor".into())
        .spawn(move || {
            let events = vec![CGEventType::FlagsChanged, CGEventType::KeyDown, CGEventType::KeyUp];
            let result = CGEventTap::with_enabled(
                CGEventTapLocation::HID,
                CGEventTapPlacement::HeadInsertEventTap,
                CGEventTapOptions::ListenOnly,
                events,
                {
                    let rt = rt.clone();
                    move |_proxy, etype, event| {
                        let shortcut = *rt.shortcut.lock().unwrap();
                        match (shortcut, etype) {
                            (PttShortcut::Fn, CGEventType::FlagsChanged) => {
                                let down = event.get_flags().contains(CGEventFlags::CGEventFlagSecondaryFn);
                                handle_edge(down, &rt, &app);
                            }
                            (PttShortcut::Key { code, shift, control, alt, command }, CGEventType::KeyDown | CGEventType::KeyUp) => {
                                let keycode = event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE) as u16;
                                if keycode == code {
                                    let flags = event.get_flags();
                                    let mods_match = flags.contains(CGEventFlags::CGEventFlagShift) == shift
                                        && flags.contains(CGEventFlags::CGEventFlagControl) == control
                                        && flags.contains(CGEventFlags::CGEventFlagAlternate) == alt
                                        && flags.contains(CGEventFlags::CGEventFlagCommand) == command;
                                    if mods_match {
                                        handle_edge(matches!(etype, CGEventType::KeyDown), &rt, &app);
                                    }
                                }
                            }
                            _ => {}
                        }
                        CallbackResult::Keep
                    }
                },
                || CFRunLoop::run_current(),
            );
            if result.is_err() {
                eprintln!("[host] push-to-talk: could not install the key monitor (Input Monitoring permission not granted)");
            }
        })
        .expect("spawn ptt-monitor thread");
}
