/**
 * Speaking Alpha's replies aloud. Native macOS speech (`say`, via the host's `tts_speak`/
 * `tts_stop` — see `apps/desktop/src-tauri/src/speech.rs`) under Tauri; `window.speechSynthesis`
 * on the web. Either way `useTts` reports whether it is currently speaking, so the avatar's mouth
 * can move (`Character` mood "talking") in step with real audio instead of a fixed timer.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { hasTauri } from "../core/session";

const KEY = "alpha.tts.enabled";

/** "Speak replies" default: on. */
export function speakEnabled(): boolean {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw === null ? true : raw === "1";
  } catch {
    return true;
  }
}

export function setSpeakEnabled(on: boolean): void {
  try {
    window.localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* per-window convenience only */
  }
}

/** `speak(text)` says it aloud (replacing anything already speaking); `stop()` cancels at once —
 *  used for barge-in, when the person starts talking again. `speaking` tracks real start/end. */
export function useTts() {
  const [speaking, setSpeaking] = useState(false);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (!hasTauri()) return;
    let disposed = false;
    const unlisten: Array<() => void> = [];
    void import("@tauri-apps/api/event").then(({ listen }) => {
      if (disposed) return;
      void listen("tts://start", () => setSpeaking(true)).then((un) => (disposed ? un() : unlisten.push(un)));
      void listen("tts://end", () => setSpeaking(false)).then((un) => (disposed ? un() : unlisten.push(un)));
    });
    return () => {
      disposed = true;
      unlisten.forEach((un) => un());
    };
  }, []);

  const stop = useCallback(() => {
    if (hasTauri()) {
      void import("@tauri-apps/api/core")
        .then(({ invoke }) => invoke("tts_stop"))
        .catch(() => undefined);
      return;
    }
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    utterance.current = null;
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (!speakEnabled() || !text.trim()) return;
      if (hasTauri()) {
        void import("@tauri-apps/api/core")
          .then(({ invoke }) => invoke("tts_speak", { text }))
          .catch(() => undefined);
        return;
      }
      if (typeof window === "undefined" || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.onstart = () => setSpeaking(true);
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      utterance.current = u;
      window.speechSynthesis.speak(u);
    },
    [],
  );

  useEffect(() => () => stop(), [stop]);
  return { speaking, speak, stop };
}
