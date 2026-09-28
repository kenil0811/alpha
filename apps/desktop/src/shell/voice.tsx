/**
 * Speaking instead of typing: one button that starts listening on a click, shows that it is
 * listening, puts words into the field as they come, and stops on the next click. Uses the
 * browser's own recognition when the window offers it; otherwise it points at the Mac's
 * dictation, which works in any text field.
 */
import { useCallback, useEffect, useRef, useState } from "react";

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

/**
 * `onText(final, interim)` is called as words arrive: `final` is everything settled since
 * listening started, `interim` the words still being recognised.
 */
export function useSpeech(onText: (final: string, interim: string) => void) {
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

/** The mic itself: red and pulsing while it listens, quiet otherwise. */
export function MicButton({ listening, supported, onToggle, small = false }: { listening: boolean; supported: boolean; onToggle: () => void; small?: boolean }) {
  const title = supported ? (listening ? "Stop listening" : "Speak instead of typing") : "Speaking isn't available in this window; press your Mac's dictation key instead";
  return (
    <button type="button" className={`iconbtn${small ? " iconbtn--sm" : ""}${listening ? " iconbtn--live" : ""}`} title={title} aria-label={listening ? "Stop listening" : "Speak"} aria-pressed={listening} onClick={onToggle} disabled={!supported}>
      <span aria-hidden="true">{listening ? "●" : "🎙"}</span>
      {listening ? <span className="live__word">Listening</span> : null}
    </button>
  );
}

/** Read the assistant's replies aloud with the Mac's own voice (Settings: "Read replies aloud").
 *  Only a reply that arrives while the conversation is on screen is spoken, never one that was
 *  already there when it was opened. */
export function useSpeakReplies(conversationId: string | null, reply: string | null, enabled: boolean): void {
  const last = useRef<{ id: string | null; reply: string | null } | null>(null);
  useEffect(() => {
    const previous = last.current;
    last.current = { id: conversationId, reply };
    if (!enabled || !reply || !previous || previous.id !== conversationId || previous.reply === reply) return;
    const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
    if (!synth || typeof SpeechSynthesisUtterance === "undefined") return;
    synth.cancel();
    synth.speak(new SpeechSynthesisUtterance(reply));
  }, [conversationId, reply, enabled]);
}
