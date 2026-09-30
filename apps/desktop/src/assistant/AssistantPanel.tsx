/**
 * The assistant panel: a session with Alpha. Every message goes through the one loop in Core
 * (run, read, open, use a skill, change or make a module, or answer); a build or change comes
 * back as a card in the thread. Sessions belong to the project on screen or are global, and
 * the panel opens on the scope's latest one. Core owns every session, so leaving and coming
 * back finds the same thread.
 */
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowUp, ChevronLeft, History, Plus, RotateCw } from "lucide-react";
import { isSessionsClient, type AttachmentWire, type Conversation, type CoreClient, type Session, type SessionsClient, type SessionSummary, type SessionTurn } from "../core/client";
import { usePoll } from "../core/usePoll";
import { MicButton, useSpeech } from "../shell/voice";
import { usePushToTalk } from "../shell/ptt";
import { ConversationCard, STATE_WORDS, Thinking, requestText } from "./ConversationCard";
import { ZazooIcon } from "../ui/ZazooIcon";
import { Button, IconButton } from "../ui";
import { Markdown } from "./markdown";
import { AttachMenu, AttachmentChips, useAttachments } from "./AttachMenu";
import { toWire, useComposerDrop, usePasteAttachments } from "./attachments";
import { modelErrorOf, NotConnectedCard } from "./NotConnectedCard";
import "./assistant.css";

const EXAMPLES = [
  "Track what I eat and how much, with calories, history and trends",
  "Keep a reading list with what I thought of each book",
  "Keep a list of job openings I find and what I did about each",
];

/** Where the panel is: the project (or none) its sessions belong to, and the module in view. */
export interface AssistantScope {
  projectId: string | null;
  projectName?: string | null;
  /** The module on screen: a hint for the loop, and what a change request is about. */
  appId?: string | null;
  moduleName?: string | null;
  moduleHint?: string | null;
}

export function AssistantPanel({
  client,
  scope = { projectId: null },
  sessionId = null,
  onSelectSession,
  conversationId = null,
  onSelectConversation,
  onOpenApp,
  headerStart,
  headerEnd,
  draft,
}: {
  client: CoreClient;
  scope?: AssistantScope;
  /** The session shown, chosen outside the panel so it survives navigation and reopening. */
  sessionId?: string | null;
  onSelectSession?: (id: string | null) => void;
  /** A conversation opened on its own (an earlier request of a module), outside any session. */
  conversationId?: string | null;
  onSelectConversation?: (id: string | null) => void;
  onOpenApp?: (appId: string) => void;
  /** Left slot of the header (the shell's collapse toggle). */
  headerStart?: ReactNode;
  /** Right slot of the header (the shell's Activity bell). */
  headerEnd?: ReactNode;
  /** Text to start the composer with (for example from "Ask or change"). */
  draft?: string | null;
}) {
  const sessions = isSessionsClient(client) ? client : null;
  const [ownSession, setOwnSession] = useState<string | null>(null);
  const selected = onSelectSession ? sessionId : ownSession;
  const select = onSelectSession ?? setOwnSession;
  const { session, loading, error, busy, reconnecting, send, refresh } = useSession(sessions, selected, select, scope);
  const [text, setText] = useState("");
  const attach = useAttachments();
  const onPaste = usePasteAttachments(attach.add);
  const { onDrop, onDragOver } = useComposerDrop(attach.add);
  const typedBefore = useRef("");
  const speech = useSpeech((final, interim) => setText(`${typedBefore.current} ${final} ${interim}`.replace(/\s+/g, " ").trim()));
  function toggleMic() {
    if (!speech.listening) typedBefore.current = text;
    speech.toggle();
  }
  usePushToTalk(
    useCallback(() => {
      if (!speech.listening) typedBefore.current = text;
      speech.start();
    }, [speech, text]),
    useCallback(() => speech.stop(), [speech]),
  );
  useEffect(() => {
    if (draft) setText(draft);
  }, [draft]);
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bodyRef.current?.scrollTo?.({ top: bodyRef.current.scrollHeight });
  }, [session?.turns.length, session?.state]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const clean = text.trim();
    if (!clean || busy) return;
    onSelectConversation?.(null);
    setText("");
    const wire = attach.items.map(toWire);
    attach.clear();
    await send(clean, wire);
  }

  const label = scope.moduleName ?? scope.projectName ?? "Home";
  const thinking = session?.state === "thinking";
  const cards = latestCardPerConversation(session?.turns ?? []);
  // An offer (a one-click yes) stands only on Alpha's newest turn; older ones are history.
  const lastAlpha = [...(session?.turns ?? [])].reverse().find((t) => t.role === "alpha")?.turn_id ?? null;

  return (
    <aside className="assist" aria-label="Chief of Staff">
      <div className="assist__head">
        {headerStart}
        <div className="assist__title">
          <ZazooIcon size={32} />
          <div className="assist__titletext">
            <b>Chief of Staff</b>
            <div className="assist__ctx">{label}</div>
          </div>
        </div>
        {headerEnd ? <div className="assist__headend">{headerEnd}</div> : null}
      </div>
      {sessions ? (
        <div className="assist__toolbar">
          <SessionSwitcher client={sessions} scope={scope} selected={selected} onSelect={(id) => { onSelectConversation?.(null); select(id); }} />
        </div>
      ) : null}
      <div className="assist__body" ref={bodyRef}>
        {conversationId ? (
          <>
            <Button size="sm" variant="ghost" style={{ alignSelf: "flex-start" }} onClick={() => onSelectConversation?.(null)}>
              <ChevronLeft size={14} aria-hidden="true" /> Back to the session
            </Button>
            <ConversationCard client={client} conversationId={conversationId} onOpenApp={onOpenApp} showRequest onStartOver={(t) => { setText(t); onSelectConversation?.(null); }} />
          </>
        ) : !session ? (
          selected && loading ? (
            <p className="panel__hint" role="status">
              Opening the session…
            </p>
          ) : (
            <>
              <div className="msg msg--ai">
                {scope.moduleName ? (
                  <>
                    I'm looking at <b>{scope.moduleName}</b>. Ask about it, tell me to run something, or describe what to change or add and Alpha rebuilds it in place. Everything already saved in it is kept.
                    {scope.moduleHint ? <div className="faint" style={{ marginTop: 6 }}>{scope.moduleHint}</div> : null}
                  </>
                ) : scope.projectName ? (
                  <>
                    This session is about <b>{scope.projectName}</b>. Ask anything about it, tell me to do something with its modules, or describe something new to make for it.
                  </>
                ) : (
                  <>Tell me what you want to keep track of, automate or get done. I'll ask at most a couple of questions, then build it.</>
                )}
              </div>
              {!scope.moduleName && !scope.projectName ? (
                <div className="assist-empty__chips" aria-label="Examples">
                  {EXAMPLES.map((example) => (
                    <Button key={example} variant="outline" className="assist-empty__chip" onClick={() => setText(example)}>
                      {example}
                    </Button>
                  ))}
                </div>
              ) : null}
              {scope.appId ? <ModuleThread client={client} appId={scope.appId} onOpen={(id) => onSelectConversation?.(id)} /> : null}
              {sessions ? <EarlierSessions client={sessions} scope={scope} onOpen={select} /> : null}
            </>
          )
        ) : (
          <>
            {session.summary ? (
              <details className="notes">
                <summary className="faint">Earlier in this session (Alpha's notes)</summary>
                <p>{session.summary}</p>
              </details>
            ) : null}
            {session.turns.map((turn, index) =>
              turn.role === "user" ? (
                <div key={turn.turn_id} className="msg msg--user">
                  {turn.text}
                  {turn.attachments?.length ? (
                    <div className="attach-chips" style={{ marginTop: 6 }}>
                      {turn.attachments.map((a, i) => (
                        <span key={i} className="attach-chip">
                          <span className="attach-chip__name">{a.name}</span>
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : turn.kind === "work" && turn.conversation_id ? (
                cards.get(turn.conversation_id) === turn.turn_id ? (
                  <ConversationCard key={turn.turn_id} client={client} conversationId={turn.conversation_id} onOpenApp={onOpenApp} onStartOver={setText} />
                ) : (
                  <div key={turn.turn_id} className="msg msg--ai faint">
                    {turn.text}
                  </div>
                )
              ) : modelErrorOf(turn.detail) ? (
                <NotConnectedCard
                  key={turn.turn_id}
                  info={modelErrorOf(turn.detail)!}
                  client={client}
                  onResend={() => void send(precedingUserText(session.turns, index))}
                />
              ) : (
                <div key={turn.turn_id} className="msg msg--ai">
                  <Markdown text={turn.text} />
                  {turn.open?.app_id && onOpenApp ? (
                    <div className="row" style={{ marginTop: 6 }}>
                      <button type="button" className="btn btn--sm" onClick={() => onOpenApp(turn.open!.app_id!)}>
                        Open it
                      </button>
                    </div>
                  ) : null}
                  {turn.outcome && turn.kind === "work" ? <div className="faint" style={{ marginTop: 4 }}>{turn.outcome}</div> : null}
                  {turn.turn_id === lastAlpha && offerOf(turn) ? (
                    <div className="row" style={{ marginTop: 8 }}>
                      <button type="button" className="btn btn--sm btn--primary" disabled={busy || thinking} onClick={() => void send(offerOf(turn)!.say)}>
                        {offerOf(turn)!.label}
                      </button>
                    </div>
                  ) : null}
                </div>
              ),
            )}
            {thinking ? <Thinking since={session.updated_at} label="Working on it…" /> : null}
            {reconnecting ? (
              <p className="notice notice--quiet" role="status">
                Lost contact with Alpha's runtime for a moment. Reconnecting…
              </p>
            ) : null}
          </>
        )}
        {error ? (
          <p className="notice" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      <form className="composer" onSubmit={submit} onDrop={onDrop} onDragOver={onDragOver}>
        <AttachmentChips items={attach.items} onRemove={attach.remove} />
        <div className="composer__box">
          <AttachMenu onAdd={attach.add} small />
          <textarea
            id="goal"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onPaste={onPaste}
            placeholder={session ? "Ask Chief of Staff… say what to do, ask, or describe a change" : "Ask Chief of Staff… describe what you want done"}
            aria-label="Message"
            rows={2}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void submit();
              }
            }}
          />
          <MicButton listening={speech.listening} supported={speech.supported} onToggle={toggleMic} small />
          <IconButton aria-label="Send" type="submit" disabled={busy || thinking || !text.trim()}>
            <ArrowUp size={16} />
          </IconButton>
        </div>
        <div className="composer__row">
          <span>{speech.error ?? "Replies use the model chosen in Settings → Models"}</span>
          {session ? (
            <IconButton aria-label="Refresh the session" size="sm" style={{ marginLeft: "auto" }} onClick={() => refresh()}>
              <RotateCw size={12} />
            </IconButton>
          ) : null}
          <span style={{ marginLeft: session ? 0 : "auto" }}>Enter to send · Shift+Enter for a new line</span>
        </div>
      </form>
    </aside>
  );
}

/** What Alpha offers to do on the person's yes (for example, letting a module use a sign-in). */
function offerOf(turn: SessionTurn): { label: string; say: string } | null {
  const offer = turn.detail?.offer as { label?: unknown; say?: unknown } | undefined;
  return offer && typeof offer.label === "string" && typeof offer.say === "string" ? { label: offer.label, say: offer.say } : null;
}

/** Where a scope's sessions live: a project's, a module's own (outside any project), or global. */
function scopeName(scope: AssistantScope): "project" | "module" | "global" {
  if (scope.projectId) return "project";
  return scope.appId ? "module" : "global";
}

/** The message a "not connected" card's Try again / I've signed in resends: the person's own
 *  turn right before it. */
function precedingUserText(turns: SessionTurn[], index: number): string {
  for (let i = index - 1; i >= 0; i--) if (turns[i].role === "user") return turns[i].text;
  return "";
}

/** Only the newest turn about a conversation draws its full card; earlier ones are one line. */
function latestCardPerConversation(turns: SessionTurn[]): Map<string, string> {
  const latest = new Map<string, string>();
  for (const turn of turns) if (turn.kind === "work" && turn.conversation_id) latest.set(turn.conversation_id, turn.turn_id);
  return latest;
}

/**
 * The selected session, loaded from Core and polled while Alpha is working on it. Sending
 * with no session yet makes one in the panel's scope first.
 */
function useSession(client: SessionsClient | null, selectedId: string | null, onSelect: (id: string | null) => void, scope: AssistantScope) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!client || !selectedId) {
      setSession(null);
      return;
    }
    if (session?.session_id === selectedId) return;
    let cancelled = false;
    setLoading(true);
    client
      .getSession(selectedId)
      .then((found) => {
        if (!cancelled) setSession(found);
      })
      .catch(() => {
        if (!cancelled) onSelect(null); // gone (another data directory, or archived elsewhere)
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, selectedId, session?.session_id, onSelect]);

  const thinking = client && session?.state === "thinking" ? session.session_id : null;
  const { reconnecting } = usePoll(thinking, () => client!.getSession(thinking!), setSession);

  const refresh = useCallback(async () => {
    if (!client || !session) return;
    try {
      setSession(await client.getSession(session.session_id));
    } catch {
      /* the next poll or send will say */
    }
  }, [client, session]);

  const send = useCallback(
    async (text: string, attachments?: AttachmentWire[]) => {
      if (!client) {
        setError("This runtime cannot hold sessions yet.");
        return;
      }
      setError(null);
      setBusy(true);
      try {
        let id = session?.session_id ?? selectedId;
        if (!id) {
          const made = await client.createSession({ project_id: scope.projectId, focus_app_id: scope.appId ?? null });
          id = made.session_id;
          onSelect(id);
        }
        setSession(await client.sendSession(id, text, scope.appId ?? null, attachments));
      } catch (e) {
        setError(`Could not send: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setBusy(false);
      }
    },
    [client, onSelect, scope.appId, scope.projectId, selectedId, session],
  );

  return { session, loading, error, busy, reconnecting, send, refresh };
}

/** The sessions of this scope, to switch between, and a new one. */
function SessionSwitcher({ client, scope, selected, onSelect }: { client: SessionsClient; scope: AssistantScope; selected: string | null; onSelect: (id: string | null) => void }) {
  const [items, setItems] = useState<SessionSummary[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    client
      .listSessions(scopeName(scope), scope.projectId, scope.appId)
      .then((all) => {
        if (!cancelled) setItems(all.filter((s) => s.origin === "shell"));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client, open, scope.projectId, scope.appId, scope]);
  return (
    <div className="switcher">
      <Button size="sm" variant="outline" className="switcher__history" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label="Sessions">
        <History size={14} aria-hidden="true" /> Chat history
      </Button>
      <IconButton aria-label="New session" onClick={() => onSelect(null)}>
        <Plus size={16} />
      </IconButton>
      {open ? (
        <nav className="switcher__menu card" aria-label="Sessions">
          {items.length === 0 ? <p className="panel__hint" style={{ padding: 10 }}>No sessions here yet.</p> : null}
          <ul>
            {items.map((s) => (
              <li key={s.session_id}>
                <button type="button" className={`recent__item${s.session_id === selected ? " recent__item--current" : ""}`} onClick={() => { setOpen(false); onSelect(s.session_id); }}>
                  <span className="recent__text">{s.title ?? "Untitled session"}</span>
                  <span className="recent__state">{when(s.updated_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}

/** Earlier sessions in this scope, newest first, for the empty state. */
function EarlierSessions({ client, scope, onOpen }: { client: SessionsClient; scope: AssistantScope; onOpen: (id: string) => void }) {
  const [items, setItems] = useState<SessionSummary[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    client
      .listSessions(scopeName(scope), scope.projectId, scope.appId)
      .then((all) => {
        if (!cancelled) setItems(all.filter((s) => s.origin === "shell").slice(0, 8));
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, scope.projectId, scope.appId, scope]);
  if (!items?.length) return null;
  return (
    <nav aria-label="Earlier sessions" className="recent">
      <h3 className="recent__title">Earlier sessions</h3>
      <ul>
        {items.map((s) => (
          <li key={s.session_id}>
            <button type="button" className="recent__item" onClick={() => onOpen(s.session_id)}>
              <span className="recent__text">{s.title ?? "Untitled session"}</span>
              <span className={s.state === "thinking" ? "recent__state recent__state--busy" : "recent__state"}>{s.state === "thinking" ? "Working" : when(s.updated_at)}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** A module's own history: the request that made it and every change since, newest first. */
function ModuleThread({ client, appId, onOpen }: { client: CoreClient; appId: string; onOpen: (id: string) => void }) {
  const [items, setItems] = useState<Conversation[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    client
      .appConversations(appId)
      .then((all) => {
        if (!cancelled) setItems(all);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, appId]);
  if (!items?.length) return null;
  return (
    <nav aria-label="This module's requests" className="recent">
      <h3 className="recent__title">This module's requests</h3>
      <ul>
        {items.map((c) => (
          <li key={c.conversation_id}>
            <button type="button" className="recent__item" onClick={() => onOpen(c.conversation_id)}>
              <span className="recent__text">{requestText(c)}</span>
              <span className="recent__state">{c.change_of ? "Change" : "Made it"} · {STATE_WORDS[c.state]}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function when(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
