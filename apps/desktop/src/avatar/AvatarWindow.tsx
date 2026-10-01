/**
 * The desktop assistant: Alpha's character in a small always-on-top window. A click opens a
 * bubble where the person types or speaks one sentence and Alpha does it at once (run, read,
 * open, change, build) and says what happened. Anything that needs the full window (a module
 * to look at, a conversation to follow) is handed to the main window, which comes forward.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";
import type { ActClient, ActTurn } from "../core/client";
import { MicButton, useSpeech } from "../shell/voice";
import { usePushToTalk } from "../shell/ptt";
import { useTts } from "../shell/tts";
import { AttachMenu, AttachmentChips, useAdvanced, useAttachments } from "../assistant/AttachMenu";
import { autoGrow, toWire, useComposerDrop, usePasteAttachments } from "../assistant/attachments";
import { NotConnectedCard } from "../assistant/NotConnectedCard";
import { IconButton } from "../ui";
import { Character, type Mood } from "./Character";

export const HANDOFF_KEY = "alpha.handoff";

/** What the avatar asks the host to do; absent outside Tauri (tests, browser). */
export interface AvatarHost {
  layout(expanded: boolean): Promise<void>;
  showMain(): Promise<void>;
}

export interface Handoff {
  app_id?: string | null;
  tab_id?: string | null;
  conversation_id?: string | null;
  session_id?: string | null;
  at: number;
}

export function AvatarWindow({ client, host, greeting = "Tell me what to do: log a meal, check the boards, open a project, or ask for something new." }: { client: ActClient; host?: AvatarHost; greeting?: string }) {
  const [expanded, setExpanded] = useState(false);
  const [turns, setTurns] = useState<ActTurn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [mood, setMood] = useState<Mood>("idle");
  const [error, setError] = useState<string | null>(null);
  const [bubble, setBubble] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bubbleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attach = useAttachments();
  const onPaste = usePasteAttachments(attach.add);
  const { onDrop, onDragOver } = useComposerDrop(attach.add);
  const advanced = useAdvanced("avatar", client);

  useEffect(() => {
    client
      .recentActs()
      .then(setTurns)
      .catch(() => undefined);
  }, [client]);
  useEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight });
  }, [turns, expanded]);

  const toggle = useCallback(async () => {
    const next = !expanded;
    try {
      await host?.layout(next);
    } catch {
      /* the window keeps its size; the panel still works */
    }
    setExpanded(next);
    if (next) setTimeout(() => inputRef.current?.focus(), 50);
  }, [expanded, host]);

  // Drag the avatar itself: past a small threshold the window follows the pointer so the
  // avatar's centre sits under it; a press without movement stays a click.
  const dragged = useRef(false);
  const press = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const dragHandlers = {
    onPointerDown: (e: React.PointerEvent<HTMLButtonElement>) => {
      if (e.button !== 0) return;
      const r = e.currentTarget.getBoundingClientRect();
      press.current = { x: e.screenX, y: e.screenY, cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
      dragged.current = false;
      e.currentTarget.setPointerCapture?.(e.pointerId);
    },
    onPointerMove: (e: React.PointerEvent<HTMLButtonElement>) => {
      const p = press.current;
      if (!p) return;
      if (!dragged.current && Math.hypot(e.screenX - p.x, e.screenY - p.y) < 4) return;
      dragged.current = true;
      const x = e.screenX - p.cx;
      const y = e.screenY - p.cy;
      void import("@tauri-apps/api/window")
        .then(({ getCurrentWindow, LogicalPosition }) => getCurrentWindow().setPosition(new LogicalPosition(Math.round(x), Math.round(y))))
        .catch(() => undefined);
    },
    onPointerUp: (e: React.PointerEvent<HTMLButtonElement>) => {
      press.current = null;
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    },
  };

  const tts = useTts();
  const say = useCallback(
    (reply: string, tone: Mood) => {
      setMood(tone);
      setBubble(reply);
      if (tone === "talking") tts.speak(reply);
      if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
      bubbleTimer.current = setTimeout(() => {
        setBubble(null);
        setMood("idle");
      }, 9000);
    },
    [tts],
  );

  const send = useCallback(
    async (sentence: string) => {
      const clean = sentence.trim();
      if (!clean || busy) return;
      setBusy(true);
      setError(null);
      setMood("thinking");
      setText("");
      const wire = attach.items.map(toWire);
      attach.clear();
      if (inputRef.current) inputRef.current.style.height = "auto";
      try {
        const turn = await client.act(clean, undefined, wire, { accessMode: advanced.accessMode, model: advanced.model ?? undefined });
        setTurns((all) => [...all, turn].slice(-30));
        say(turn.reply, turn.kind === "answer" && /can't|couldn't|didn't/i.test(turn.reply) ? "sorry" : "talking");
        if (turn.open && (turn.open.app_id || turn.open.conversation_id || turn.open.session_id)) {
          const handoff: Handoff = { ...turn.open, at: Date.now() };
          try {
            localStorage.setItem(HANDOFF_KEY, JSON.stringify(handoff));
          } catch {
            /* no storage: the main window is not told */
          }
          void host?.showMain();
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setMood("sorry");
      } finally {
        setBusy(false);
      }
    },
    [busy, client, host, say, attach, advanced.accessMode, advanced.model],
  );

  const speech = useSpeech((final, interim) => {
    setText(final || interim);
    if (final) void send(final);
  });
  useEffect(() => {
    setMood((m) => (speech.listening ? "listening" : m === "listening" ? "idle" : m));
    // Barge-in: the person started talking, so whatever Alpha was saying stops at once.
    if (speech.listening) tts.stop();
  }, [speech.listening, tts]);
  usePushToTalk(
    useCallback(() => {
      if (!expanded) void toggle();
      speech.start();
    }, [expanded, toggle, speech]),
    useCallback(() => speech.stop(), [speech]),
  );

  // The mouth moves for as long as speech is actually playing, on top of whatever mood the last
  // reply set (its tone still colours the pose/expression via `EMOTION`).
  const shownMood: Mood = speech.listening ? "listening" : tts.speaking ? "talking" : mood;

  return (
    <div className={`avatar${expanded ? " avatar--open" : ""}`} onKeyDown={(e) => e.key === "Escape" && expanded && void toggle()}>
      {expanded ? (
        <section className="avatar__panel" aria-label="Alpha assistant">
          <header className="avatar__head" data-tauri-drag-region title="Say what to do">
            <b data-tauri-drag-region>Chief of Staff</b>
            <button type="button" className="iconbtn iconbtn--sm" aria-label="Close" onClick={() => void toggle()}>
              ×
            </button>
          </header>
          <div className="avatar__turns" ref={listRef}>
            {turns.length === 0 ? <p className="panel__hint">{greeting}</p> : null}
            {turns.map((turn, index) => (
              <div key={turn.turn_id} className="avatar__turn">
                <div className="avatar__said">
                  {turn.text}
                  {turn.attachments?.length ? (
                    <span className="faint"> · {turn.attachments.map((a) => a.name).join(", ")}</span>
                  ) : null}
                </div>
                {turn.model_error ? (
                  <NotConnectedCard info={turn.model_error} client={client} onResend={() => void send(turn.text)} auto={index === turns.length - 1} />
                ) : (
                  <div className={`avatar__reply avatar__reply--${turn.kind}`}>
                    {turn.reply}
                    {turn.app_name ? <span className="faint"> · {turn.app_name}</span> : null}
                  </div>
                )}
              </div>
            ))}
            {busy ? (
              <p className="panel__hint" role="status">
                Working on it…
              </p>
            ) : null}
            {error ? (
              <p className="notice" role="alert">
                {error}
              </p>
            ) : null}
          </div>
          <AttachmentChips items={attach.items} onRemove={attach.remove} />
          <form
            className="avatar__ask"
            onSubmit={(e) => {
              e.preventDefault();
              void send(text);
            }}
            onDrop={onDrop}
            onDragOver={onDragOver}
          >
            <AttachMenu
              onAdd={attach.add}
              small
              advanced={{
                accessMode: advanced.accessMode,
                onAccessModeChange: advanced.setAccessMode,
                model: advanced.model,
                onModelChange: advanced.setModel,
                client,
              }}
            />
            <textarea
              ref={inputRef}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                autoGrow(e.currentTarget);
              }}
              onPaste={onPaste}
              placeholder="Ask Chief of Staff…"
              aria-label="Message"
              rows={1}
              disabled={busy}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(text);
                }
              }}
            />
            <MicButton listening={speech.listening} supported={speech.supported} onToggle={speech.toggle} small />
            <IconButton aria-label="Send" type="button" size="sm" className="avatar__send" disabled={busy || !text.trim()} onClick={() => void send(text)}>
              <ArrowUp size={14} aria-hidden="true" />
            </IconButton>
          </form>
        </section>
      ) : null}
      <div className="avatar__dock">
        {!expanded && bubble ? (
          <div className="avatar__bubble" role="status">
            {bubble}
          </div>
        ) : null}
        <div className="avatar__grip" data-tauri-drag-region title="Drag to move Alpha" aria-hidden="true">
          ⋯
        </div>
        <button type="button" className="avatar__button" {...dragHandlers} onClick={() => (dragged.current ? (dragged.current = false) : void toggle())} aria-label={expanded ? "Hide Alpha's panel" : "Ask Alpha"} aria-expanded={expanded} title={expanded ? "Hide" : "Ask Alpha"}>
          <Character mood={busy ? "thinking" : shownMood} size={expanded ? 56 : 88} />
        </button>
      </div>
    </div>
  );
}
