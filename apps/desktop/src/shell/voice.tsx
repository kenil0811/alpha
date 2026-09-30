/**
 * Speaking instead of typing: one button that starts listening on a click, shows that it is
 * listening, puts words into the field as they come, and stops on the next click. Three ways to
 * listen, picked by the "Transcription" setting (Settings -> Desktop):
 *  - "On this Mac": Tauri drives the native host's speech-to-text (`stt_start`/`stt_stop`,
 *    events `stt://partial`/`stt://final`/`stt://error` — see `apps/desktop/src-tauri/src/speech.rs`),
 *    because WKWebView exposes neither `SpeechRecognition` nor `webkitSpeechRecognition`; on the
 *    plain web it uses the browser's own recognition when offered.
 *  - "Groq Whisper" / "OpenAI": records with `MediaRecorder` (works in WKWebView on macOS 14.4+
 *    with mic permission, and in any browser) and posts the clip to Core's `/api/transcribe`,
 *    which calls whichever key is saved in Settings -> Models.
 *  - "Automatic" (default): cloud when a Groq or OpenAI key is saved, otherwise on-this-Mac.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { hasTauri, resolveSession } from "../core/session";

export type TranscriptionMode = "automatic" | "native" | "groq" | "openai";
const MODE_KEY = "alpha.transcription.mode";

export function readTranscriptionMode(): TranscriptionMode {
  try {
    const raw = window.localStorage.getItem(MODE_KEY);
    return raw === "native" || raw === "groq" || raw === "openai" ? raw : "automatic";
  } catch {
    return "automatic";
  }
}

export function writeTranscriptionMode(mode: TranscriptionMode): void {
  try {
    window.localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* per-window convenience only */
  }
}

// The setting's "openai" reads better than Core's Keychain provider id, which is "chatgpt"
// (the same key ChatGPT sign-in uses) — see alpha/models/accounts.py PROVIDERS.
function keychainProviderId(mode: "groq" | "openai"): "groq" | "chatgpt" {
  return mode === "openai" ? "chatgpt" : "groq";
}

/** Whether a Groq or OpenAI key is saved, for "Automatic" to decide cloud vs. on-this-Mac. */
async function cloudProviderAvailable(): Promise<boolean> {
  try {
    const resolution = await resolveSession();
    if (resolution.kind !== "ready") return false;
    const res = await fetch(`${resolution.session.baseUrl}/api/model-accounts`, {
      headers: { Authorization: `Bearer ${resolution.session.token}` },
    });
    if (!res.ok) return false;
    const body = (await res.json()) as { providers?: { id: string; state: string }[] };
    return (body.providers ?? []).some((p) => (p.id === "groq" || p.id === "chatgpt") && p.state === "key_saved");
  } catch {
    return false;
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

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

/** Records with `MediaRecorder` and, on stop, posts the clip to Core's `/api/transcribe`
 *  (whichever of Groq/OpenAI has a saved key — see Settings -> Models). One clip per
 *  start/stop; `onText` is called once, with the whole transcript as `final`. */
function useCloudSpeech(onText: (final: string, interim: string) => void, preferred?: "groq" | "chatgpt") {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const settled = useRef("");
  const latest = useRef(onText);
  latest.current = onText;
  const preferredRef = useRef(preferred);
  preferredRef.current = preferred;

  const supported = typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  const stop = useCallback(() => {
    const rec = recorder.current;
    if (rec && rec.state !== "inactive") rec.stop();
    setListening(false);
  }, []);

  const start = useCallback(() => {
    if (!supported) return;
    setError(null);
    void navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        const chunks: Blob[] = [];
        const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";
        const rec = new MediaRecorder(stream, { mimeType: mime });
        rec.ondataavailable = (e) => {
          if (e.data.size) chunks.push(e.data);
        };
        rec.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          setListening(false);
          void transcribeClip(new Blob(chunks, { type: mime }), mime, preferredRef.current)
            .then((text) => {
              settled.current = `${settled.current} ${text}`.trim();
              latest.current(settled.current, "");
            })
            .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
        };
        recorder.current = rec;
        settled.current = "";
        rec.start();
        setListening(true);
      })
      .catch(() => {
        setError("Alpha needs permission to use the microphone.");
        setListening(false);
      });
  }, [supported]);

  useEffect(() => () => stop(), [stop]);
  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);
  return { supported, listening, error, start, stop, toggle };
}

async function transcribeClip(blob: Blob, mime: string, preferred?: "groq" | "chatgpt"): Promise<string> {
  const resolution = await resolveSession();
  if (resolution.kind !== "ready") throw new Error("Alpha's runtime isn't available.");
  const audio_b64 = await blobToBase64(blob);
  const res = await fetch(`${resolution.session.baseUrl}/api/transcribe`, {
    method: "POST",
    headers: { Authorization: `Bearer ${resolution.session.token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ audio_b64, mime, provider: preferred }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : "Could not transcribe.");
  }
  const data = (await res.json()) as { text?: string };
  return data.text ?? "";
}

/**
 * `onText(final, interim)` is called as words arrive: `final` is everything settled since
 * listening started, `interim` the words still being recognised. Which way it listens follows
 * the "Transcription" setting (Settings -> Desktop): a saved choice of "On this Mac", "Groq
 * Whisper" or "OpenAI", or "Automatic" (cloud when a key is saved, otherwise on this Mac).
 */
export function useSpeech(onText: (final: string, interim: string) => void) {
  // Hooks must run unconditionally and in the same order every render; the setting is fixed for
  // the life of a window (a change takes effect on the next mount), so picking the branch this
  // way never violates that.
  const [mode] = useState(readTranscriptionMode);
  const native = useNativeSpeech(onText);
  const browser = useBrowserSpeech(onText);
  const cloud = useCloudSpeech(onText, mode === "groq" || mode === "openai" ? keychainProviderId(mode) : undefined);
  const [autoCloud, setAutoCloud] = useState<boolean | null>(null);
  useEffect(() => {
    if (mode !== "automatic") return;
    let cancelled = false;
    void cloudProviderAvailable().then((ok) => {
      if (!cancelled) setAutoCloud(ok);
    });
    return () => {
      cancelled = true;
    };
  }, [mode]);

  if (mode === "groq" || mode === "openai") return cloud;
  if (mode === "native") return hasTauri() ? native : browser;
  // "automatic": while still checking, fall back to on-this-Mac rather than block the mic.
  if (autoCloud) return cloud;
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
