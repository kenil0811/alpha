/**
 * Speaking instead of typing: one button that starts listening on a click, shows that it is
 * listening, puts words into the field as they come, and stops on the next click. Inside Tauri
 * this drives the native host's speech-to-text (`stt_start`/`stt_stop`, events `stt://partial` /
 * `stt://final` / `stt://error` — see `apps/desktop/src-tauri/src/speech.rs`), because WKWebView
 * exposes neither `SpeechRecognition` nor `webkitSpeechRecognition`. On the plain web it uses the
 * browser's own recognition when offered; otherwise it points at the Mac's dictation, which works
 * in any text field.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { hasTauri } from "../core/session";

interface RecognitionResultEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}
interface Recognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: RecognitionResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  start: () => void;
  stop: () => void;
}
type RecognitionCtor = new () => Recognition;

function recognitionClass(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function speechSupported(): boolean {
  return recognitionClass() !== null;
}

function useNativeSpeech(onText: (final: string, interim: string) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const settled = useRef("");
  const latest = useRef(onText);
  latest.current = onText;

  useEffect(() => {
    if (!hasTauri()) return;
    let disposed = false;
    const unlisten: Array<() => void> = [];
    void import("@tauri-apps/api/event").then(({ listen }) => {
      if (disposed) return;
      void listen<{ text: string }>("stt://partial", (e) => latest.current(settled.current, e.payload.text)).then((un) => (disposed ? un() : unlisten.push(un)));
      void listen<{ text: string }>("stt://final", (e) => {
        settled.current = `${settled.current} ${e.payload.text}`.trim();
        latest.current(settled.current, "");
        setListening(false);
      }).then((un) => (disposed ? un() : unlisten.push(un)));
      void listen<{ text: string }>("stt://error", (e) => {
        setError(e.payload.text.startsWith("permission_denied") ? "Alpha needs permission to use the microphone." : e.payload.text || "Listening stopped.");
        setListening(false);
      }).then((un) => (disposed ? un() : unlisten.push(un)));
    });
    return () => {
      disposed = true;
      unlisten.forEach((un) => un());
    };
  }, []);

  const stop = useCallback(() => {
    setListening(false);
    void import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke("stt_stop"))
      .catch(() => undefined);
  }, []);

  const start = useCallback(() => {
    settled.current = "";
    setError(null);
    setListening(true);
    void import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke("stt_start"))
      .catch(() => {
        setError("Listening isn't available on this build.");
        setListening(false);
      });
  }, []);

  useEffect(() => () => void stop(), [stop]);
  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);
  return { supported: true, listening, error, start, stop, toggle };
}

function useBrowserSpeech(onText: (final: string, interim: string) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<Recognition | null>(null);
  const settled = useRef("");
  const latest = useRef(onText);
  latest.current = onText;

  const stop = useCallback(() => {
    active.current?.stop();
    active.current = null;
    setListening(false);
  }, []);

  const start = useCallback(() => {
    const Ctor = recognitionClass();
    if (!Ctor) return;
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = navigator.language || "en-GB";
    settled.current = "";
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const piece = e.results[i][0].transcript;
        if (e.results[i].isFinal) settled.current = `${settled.current} ${piece}`.trim();
        else interim += piece;
      }
      latest.current(settled.current, interim.trim());
    };
    r.onerror = (e) => {
      setError(e.error === "not-allowed" ? "Alpha needs permission to use the microphone." : "Listening stopped.");
      setListening(false);
      active.current = null;
    };
    r.onend = () => {
      if (active.current === r) {
        active.current = null;
        setListening(false);
      }
    };
    setError(null);
    active.current = r;
    setListening(true);
    r.start();
  }, []);

  useEffect(() => () => active.current?.stop(), []);
  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);
  return { supported: speechSupported(), listening, error, start, stop, toggle };
}

/**
 * `onText(final, interim)` is called as words arrive: `final` is everything settled since
 * listening started, `interim` the words still being recognised.
 */
export function useSpeech(onText: (final: string, interim: string) => void) {
  // Hooks must run unconditionally and in the same order every render; `hasTauri()` is fixed for
  // the life of a window, so picking the branch this way never violates that.
  const native = useNativeSpeech(onText);
  const browser = useBrowserSpeech(onText);
  return hasTauri() ? native : browser;
}

/** The mic itself: red and pulsing while it listens, quiet otherwise. */
export function MicButton({ listening, supported, onToggle, small = false }: { listening: boolean; supported: boolean; onToggle: () => void; small?: boolean }) {
  const title = supported ? (listening ? "Stop listening" : "Speak instead of typing") : "Speaking isn't available in this window; press your Mac's dictation key instead";
  return (
    <button type="button" className={`iconbtn${small ? " iconbtn--sm" : ""}${listening ? " iconbtn--live" : ""}`} title={title} aria-label={listening ? "Stop listening" : "Speak"} aria-pressed={listening} onClick={onToggle} disabled={!supported}>
      {listening ? <span aria-hidden="true">●</span> : <Mic size={14} />}
      {listening ? <span className="live__word">Listening</span> : null}
    </button>
  );
}
