/**
 * The assistant panel: the front door for new modules (request → questions → plan → build) and
 * the place to ask about, or change, the module on screen. Core owns every conversation and
 * creation, so leaving and coming back finds the same request.
 */
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CREATION_DONE, isWorkflowsClient, type Conversation, type CoreClient, type Creation, type ModelConnection } from "../core/client";
import { CreationCard } from "../workflows/CreationCard";
import { MicButton, useSpeakReplies, useSpeech } from "../shell/voice";
import { ConnectionProblem, isDisconnected } from "../shell/models";
import { BriefCard } from "./BriefCard";
import { QuestionsForm } from "./QuestionsForm";
import { useConversation } from "./useConversation";

const EXAMPLES = [
  "Track what I eat and how much, with calories, history and trends",
  "Keep a reading list with what I thought of each book",
  "Keep a list of job openings I find and what I did about each",
];

const STATE_WORDS: Record<Conversation["state"], string> = {
  thinking: "Thinking",
  waiting_for_user: "Waiting for your answers",
  briefed: "Planned",
  answered: "Answered",
  failed: "Didn't work out",
};

const CREATION_WORDS: Record<string, string> = {
  planning: "Being made",
  building: "Being made",
  checking: "Being made",
  activating: "Being made",
  active: "Ready",
  failed: "Not made",
  cancelled: "Stopped",
};

function requestText(conversation: Conversation): string {
  const first = conversation.turns.find((t) => t.role === "user");
  return String(first?.content.text ?? "");
}

export interface AssistantContext {
  /** What the panel is looking at: the module name, or null on general surfaces. */
  moduleName: string | null;
  /** The module's id: a request typed here changes that module instead of making a new one. */
  appId?: string | null;
  moduleHint?: string | null;
}

export function AssistantPanel({
  client,
  conversationId = null,
  onSelect,
  onOpenApp,
  context = { moduleName: null },
  onHide,
  draft,
  connection = null,
  onRefreshConnection,
  onOpenSettings,
  speakReplies = false,
}: {
  client: CoreClient;
  conversationId?: string | null;
  onSelect?: (id: string | null) => void;
  onOpenApp?: (appId: string) => void;
  context?: AssistantContext;
  onHide?: () => void;
  /** Text to start the composer with (for example from "Ask or change"). */
  draft?: string | null;
  /** The Claude connection as last reported; a failed turn it explains is shown as such. */
  connection?: ModelConnection | null;
  onRefreshConnection?: () => void;
  onOpenSettings?: () => void;
  /** Read new replies aloud (Settings: Voice). */
  speakReplies?: boolean;
}) {
  const [ownSelection, setOwnSelection] = useState<string | null>(null);
  const selected = onSelect ? conversationId : ownSelection;
  const select = onSelect ?? setOwnSelection;
  const { conversation, loading, error, busy, reconnecting, start, reply, retry, cancel, reset } = useConversation(client, selected, select);
  const [text, setText] = useState("");
  const [correction, setCorrection] = useState("");
  const typedBefore = useRef("");
  const speech = useSpeech((final, interim) => setText(`${typedBefore.current} ${final} ${interim}`.replace(/\s+/g, " ").trim()));
  function toggleMic() {
    if (!speech.listening) typedBefore.current = text;
    speech.toggle();
  }
  // Opened from a module, the panel is that module's thread: a conversation about something
  // else (or a new module made from Home) gives way to the module's own history.
  const appId = context.appId ?? null;
  useEffect(() => {
    if (!appId || !conversation || loading) return;
    if (conversation.change_of !== appId && creation?.app_id !== appId) select(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId]);
  const [creation, setCreation] = useState<Creation | null>(null);
  const onCreation = useCallback((c: Creation | null) => setCreation(c), []);
  useEffect(() => setCreation(null), [conversation?.conversation_id]);
  useEffect(() => {
    if (draft) setText(draft);
  }, [draft]);
  useSpeakReplies(conversation?.conversation_id ?? null, conversation?.reply ?? null, speakReplies);
  const failed = conversation?.state === "failed" ? conversation.conversation_id : null;
  useEffect(() => {
    if (failed) onRefreshConnection?.();
  }, [failed, onRefreshConnection]);
  const made = creation?.state === "active";
  const making = creation !== null && !CREATION_DONE.has(creation.state);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!text.trim()) return;
    await start(text.trim(), context.appId ?? null);
    setText("");
  }

  function startOver() {
    if (conversation) setText(requestText(conversation));
    reset();
  }

  const thinking = conversation?.state === "thinking";
  const userTurns = conversation?.turns.filter((t) => t.role === "user") ?? [];
  const changing = conversation ? Boolean(conversation.change_of) : Boolean(context.appId);
  const contextLabel = conversation ? (changing ? "Changing a module" : "New module") : context.moduleName ?? "Home";

  return (
    <aside className="assist" aria-label="Assistant">
      <div className="assist__head">
        <div className="assist__mark" aria-hidden="true">
          A
        </div>
        <div style={{ minWidth: 0 }}>
          <b>Assistant</b>
          <div className="assist__ctx">{contextLabel}</div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          {conversation ? (
            <button type="button" className="btn btn--sm" onClick={reset}>
              New request
            </button>
          ) : null}
          {onHide ? (
            <button type="button" className="iconbtn" onClick={onHide} aria-label="Hide assistant">
              ›
            </button>
          ) : null}
        </div>
      </div>
      <div className="assist__body">
        {!conversation ? (
          selected && loading ? (
            <p className="panel__hint" role="status">
              Opening your request…
            </p>
          ) : (
            <>
              <div className="msg msg--ai">
                {context.moduleName ? (
                  <>
                    I'm looking at <b>{context.moduleName}</b>. Describe what to change or add and Alpha rebuilds it in place. Everything already
                    saved in it is kept.
                    {context.moduleHint ? <div className="faint" style={{ marginTop: 6 }}>{context.moduleHint}</div> : null}
                  </>
                ) : (
                  <>Tell me what you want to keep track of, automate or get done. I'll ask at most a couple of questions, then build it.</>
                )}
              </div>
              {!context.moduleName ? (
                <div className="examples" aria-label="Examples">
                  {EXAMPLES.map((example) => (
                    <button key={example} type="button" className="example" onClick={() => setText(example)}>
                      {example}
                    </button>
                  ))}
                </div>
              ) : null}
              {context.appId ? <ModuleThread client={client} appId={context.appId} onOpen={select} /> : <RecentRequests client={client} onOpen={select} />}
            </>
          )
        ) : (
          <>
            {userTurns.length ? <div className="msg msg--user">{String(userTurns[0].content.text ?? "")}</div> : null}
            {conversation.interpretation ? (
              <div className="interpretation" aria-label="How Alpha understood it">
                <div className="msg__label">How Alpha understood it</div>
                <dl>
                  <dt>Outcome</dt>
                  <dd>{conversation.interpretation.outcome}</dd>
                  <dt>Main input</dt>
                  <dd>{conversation.interpretation.main_input}</dd>
                  <dt>Useful result</dt>
                  <dd>{conversation.interpretation.useful_result}</dd>
                </dl>
              </div>
            ) : null}
            {conversation.reply ? <div className="msg msg--ai">{conversation.reply}</div> : null}
            {thinking ? <Thinking since={conversation.updated_at} busy={busy} onStop={() => void cancel()} /> : null}
            {reconnecting ? (
              <p className="notice notice--quiet" role="status">
                Lost contact with Alpha's runtime for a moment. Reconnecting…
              </p>
            ) : null}
            {conversation.state === "failed" ? (
              <div className="failure" role={isDisconnected(connection) ? undefined : "alert"} aria-label="Alpha could not work this out">
                {connection && isDisconnected(connection) ? (
                  <ConnectionProblem connection={connection} onOpenSettings={onOpenSettings} />
                ) : (
                  <p className="notice">Alpha could not work this out: {conversation.error ?? "something went wrong"}.</p>
                )}
                <div className="row">
                  <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void retry()}>
                    Try again
                  </button>
                  <button type="button" className="btn" onClick={startOver}>
                    Start over
                  </button>
                </div>
              </div>
            ) : null}
            {conversation.state === "waiting_for_user" && conversation.questions.length ? (
              <QuestionsForm questions={conversation.questions} busy={busy} onAnswer={(answers) => reply({ answers })} onDefaults={() => reply({ use_defaults: true })} />
            ) : null}
            {conversation.current_brief && conversation.state !== "thinking" ? <BriefCard brief={conversation.current_brief} dataNotice={conversation.data_notice} /> : null}
            {conversation.state === "briefed" && conversation.delivery === "app" && (conversation.current_brief || conversation.quick_change) && isWorkflowsClient(client) ? (
              <CreationCard
                client={client}
                conversationId={conversation.conversation_id}
                briefRevision={conversation.quick_change ? 0 : (conversation.current_brief?.revision ?? 0)}
                unavailable={conversation.current_brief?.unavailable_capabilities ?? []}
                auto={Boolean(conversation.change_of)}
                onOpen={(appId) => onOpenApp?.(appId)}
                onChange={onCreation}
              />
            ) : null}
            {made ? (
              <div className="after-made" aria-label="After it was made">
                <p className="panel__hint">
                  {creation?.change_of
                    ? `${creation?.result?.name ?? creation?.app_name ?? "Your module"} is updated and its data is kept. To change it again, open it and ask there.`
                    : `${creation?.result?.name ?? creation?.app_name ?? "Your module"} is in the sidebar. To change it later, open it and describe the change here.`}
                </p>
                <div className="row">
                  <button type="button" className="btn" onClick={startOver}>
                    Describe another
                  </button>
                </div>
              </div>
            ) : null}
            {making ? <p className="panel__hint">You can change the request once this attempt finishes, or after you stop it.</p> : null}
            {!made && !making && (conversation.state === "briefed" || conversation.state === "answered" || conversation.state === "waiting_for_user") ? (
              <form
                className="correction"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!correction.trim()) return;
                  reply({ text: correction.trim() });
                  setCorrection("");
                }}
              >
                <div className="field">
                  <label htmlFor="correction">Change or add something</label>
                  <input id="correction" value={correction} onChange={(e) => setCorrection(e.target.value)} placeholder="e.g. also track protein" />
                </div>
                <div className="row">
                  <button type="submit" className="btn" disabled={busy || !correction.trim()}>
                    Send
                  </button>
                  <button type="button" className="btn" onClick={startOver}>
                    Start over
                  </button>
                </div>
              </form>
            ) : null}
          </>
        )}
        {error ? (
          <p className="notice" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      {!conversation ? (
        <form className="composer" onSubmit={submit}>
          <div className="composer__box">
            <textarea
              id="goal"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Describe what you want done…"
              aria-label="What do you want done?"
              rows={2}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void submit();
              }}
            />
            <MicButton listening={speech.listening} supported={speech.supported} onToggle={toggleMic} small />
            <button type="submit" className="btn btn--primary btn--sm" disabled={busy || !text.trim()}>
              Send
            </button>
          </div>
          <div className="composer__row">
            <span>{speech.error ?? "Uses your Claude subscription"}</span>
            <span style={{ marginLeft: "auto" }}>⌘↩ to send</span>
          </div>
        </form>
      ) : null}
    </aside>
  );
}

/** The wait, made visible: how long it has been, a word when it is longer than usual, and Stop. */
function Thinking({ since, busy, onStop }: { since: string; busy: boolean; onStop: () => void }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = new Date(since).getTime();
    const tick = () => setSeconds(Math.max(0, Math.round((Date.now() - started) / 1000)));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [since]);
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <div className="msg msg--ai" role="status">
      <div>
        Thinking about your request… <span className="faint">{clock}</span>
      </div>
      {seconds >= 90 ? <div className="faint" style={{ marginTop: 4 }}>Longer than usual. A large request or a busy model service can take a few minutes; you can stop and try again.</div> : null}
      <div className="row" style={{ marginTop: 8 }}>
        <button type="button" className="btn btn--sm" disabled={busy} onClick={onStop}>
          Stop
        </button>
      </div>
    </div>
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

/** Earlier requests, newest first, with where each one got to. */
function RecentRequests({ client, onOpen }: { client: CoreClient; onOpen: (id: string) => void }) {
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [creations, setCreations] = useState<Map<string, Creation>>(new Map());

  useEffect(() => {
    let cancelled = false;
    client
      .listConversations()
      .then((all) => {
        if (!cancelled) setItems(all.slice(0, 8));
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    if (isWorkflowsClient(client)) {
      client
        .recentCreations()
        .then((all) => {
          if (cancelled) return;
          const latest = new Map<string, Creation>();
          for (const c of [...all].reverse()) latest.set(c.conversation_id, c);
          setCreations(latest);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [client]);

  if (!items?.length) return null;
  return (
    <nav aria-label="Recent requests" className="recent">
      <h3 className="recent__title">Recent requests</h3>
      <ul>
        {items.map((c) => {
          const creation = creations.get(c.conversation_id);
          const where = creation ? CREATION_WORDS[creation.state] ?? creation.label : STATE_WORDS[c.state];
          const inProgress = creation ? !CREATION_DONE.has(creation.state) : c.state === "thinking";
          return (
            <li key={c.conversation_id}>
              <button type="button" className="recent__item" onClick={() => onOpen(c.conversation_id)}>
                <span className="recent__text">{requestText(c) || "Untitled request"}</span>
                <span className={inProgress ? "recent__state recent__state--busy" : "recent__state"}>{where}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
