/**
 * Push-to-talk: hold a key to speak to Alpha instead of typing. The shortcut (Fn by default, or
 * a recorded key/combination) is chosen in Settings, kept in localStorage for this window, and
 * mirrored to the native host, which is the thing that actually watches for it (Fn is a modifier
 * flag no browser key event ever reports, so listening happens in Rust; see
 * `apps/desktop/src-tauri/src/ptt.rs`). The host emits `ptt://start` / `ptt://stop` Tauri events;
 * `usePushToTalk` below is how a window's voice input hooks into those.
 */
import { useEffect, useRef } from "react";
import { hasTauri } from "../core/session";

export type PttShortcut =
  | { mode: "fn" }
  | { mode: "key"; code: number; shift: boolean; control: boolean; alt: boolean; command: boolean; label: string };

const KEY = "alpha.ptt.shortcut";
const DEFAULT_SHORTCUT: PttShortcut = { mode: "fn" };

export function readShortcut(): PttShortcut {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as PttShortcut) : DEFAULT_SHORTCUT;
  } catch {
    return DEFAULT_SHORTCUT;
  }
}

/** Saves the choice for this window and tells the host to start watching for it. */
export function writeShortcut(shortcut: PttShortcut): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(shortcut));
  } catch {
    /* per-window convenience only */
  }
  void pushShortcutToHost(shortcut);
}

async function pushShortcutToHost(shortcut: PttShortcut): Promise<void> {
  if (!hasTauri()) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("ptt_set_shortcut", { shortcut });
  } catch {
    /* older host build without the command, or permission plumbing not ready yet */
  }
}

/** macOS virtual keycodes for the keys the recorder can capture, keyed by the browser's
 *  `KeyboardEvent.code` (a physical key, unlike `.key` which changes with layout/modifiers).
 *  Covers letters, digits, punctuation, arrows and function keys — enough for a person to pick
 *  a comfortable combo. Modifier keys themselves (Shift, Fn, ...) are deliberately absent: they
 *  are read off `event.shiftKey` etc. as the combo's modifiers, not as the key itself. */
const CG_KEYCODES: Record<string, number> = {
  KeyA: 0x00, KeyS: 0x01, KeyD: 0x02, KeyF: 0x03, KeyH: 0x04, KeyG: 0x05, KeyZ: 0x06, KeyX: 0x07,
  KeyC: 0x08, KeyV: 0x09, KeyB: 0x0b, KeyQ: 0x0c, KeyW: 0x0d, KeyE: 0x0e, KeyR: 0x0f, KeyY: 0x10,
  KeyT: 0x11, Digit1: 0x12, Digit2: 0x13, Digit3: 0x14, Digit4: 0x15, Digit6: 0x16, Digit5: 0x17,
  Equal: 0x18, Digit9: 0x19, Digit7: 0x1a, Minus: 0x1b, Digit8: 0x1c, Digit0: 0x1d,
  BracketRight: 0x1e, KeyO: 0x1f, KeyU: 0x20, BracketLeft: 0x21, KeyI: 0x22, KeyP: 0x23,
  Enter: 0x24, KeyL: 0x25, KeyJ: 0x26, Quote: 0x27, KeyK: 0x28, Semicolon: 0x29, Backslash: 0x2a,
  Comma: 0x2b, Slash: 0x2c, KeyN: 0x2d, KeyM: 0x2e, Period: 0x2f, Tab: 0x30, Space: 0x31,
  Backquote: 0x32, Backspace: 0x33, Escape: 0x35, ArrowLeft: 0x7b, ArrowRight: 0x7c,
  ArrowDown: 0x7d, ArrowUp: 0x7e, F1: 0x7a, F2: 0x78, F3: 0x63, F4: 0x76, F5: 0x60, F6: 0x61,
  F7: 0x62, F8: 0x64, F9: 0x65, F10: 0x6d, F11: 0x67, F12: 0x6f,
};

const KEY_LABELS: Record<string, string> = {
  Space: "Space", Enter: "Return", Tab: "Tab", Escape: "Esc", Backspace: "Delete",
  ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓",
};

/** The macOS keycode for a recorded key, or `null` if it is a modifier/unmapped key (the
 *  recorder should keep waiting rather than accept it as the shortcut's own key). */
export function keycodeFor(code: string): number | null {
  return code in CG_KEYCODES ? CG_KEYCODES[code] : null;
}

export function shortcutLabel(shortcut: PttShortcut): string {
  if (shortcut.mode === "fn") return "Fn";
  const mods = `${shortcut.control ? "⌃" : ""}${shortcut.alt ? "⌥" : ""}${shortcut.shift ? "⇧" : ""}${shortcut.command ? "⌘" : ""}`;
  return `${mods}${shortcut.label}`;
}

export function labelFor(code: string): string {
  return KEY_LABELS[code] ?? code.replace(/^(Key|Digit)/, "");
}

/** Wires a window's voice input to the host's push-to-talk events: `onStart` when the configured
 *  key has been held past the hold threshold, `onStop` on release. A no-op outside Tauri (web
 *  preview, tests) — the caller's normal mic button keeps working either way. */
export function usePushToTalk(onStart: () => void, onStop: () => void): void {
  const startRef = useRef(onStart);
  const stopRef = useRef(onStop);
  startRef.current = onStart;
  stopRef.current = onStop;
  useEffect(() => {
    if (!hasTauri()) return;
    let disposed = false;
    const unlisten: Array<() => void> = [];
    void pushShortcutToHost(readShortcut());
    void import("@tauri-apps/api/event").then(({ listen }) => {
      if (disposed) return;
      void listen("ptt://start", () => startRef.current()).then((un) => (disposed ? un() : unlisten.push(un)));
      void listen("ptt://stop", () => stopRef.current()).then((un) => (disposed ? un() : unlisten.push(un)));
    });
    return () => {
      disposed = true;
      unlisten.forEach((un) => un());
    };
  }, []);
}
