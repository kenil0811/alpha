/**
 * The assistant panel: the front door for new modules (request → questions → plan → build) and
 * the place to ask about, or change, the module on screen. Core owns every conversation and
 * creation, so leaving and coming back finds the same request.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowUp, Plus } from "lucide-react";
import { CREATION_DONE, isWorkflowsClient, type Conversation, type CoreClient, type Creation } from "../core/client";
import { CreationCard } from "../workflows/CreationCard";
import { MicButton, useSpeech } from "../shell/voice";
import { ZazooIcon } from "../ui/ZazooIcon";
import { Button, IconButton, StandardDropdown, type StandardDropdownOption } from "../ui";
import { BriefCard } from "./BriefCard";
import { QuestionsForm } from "./QuestionsForm";
import { Markdown } from "./markdown";
import { useConversation } from "./useConversation";
import "./assistant.css";

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

function turnText(turn: Conversation["turns"][number]): string {
  const text = turn.content.text;
  if (typeof text === "string" && text.trim()) return text;
  const answers = turn.content.answers;
  if (answers && typeof answers === "object") {
    return Object.values(answers as Record<string, unknown>)
      .map(String)
      .join(", ");
  }
  return "";
}

export interface AssistantContext {
  /** What the panel is looking at: the module name, or null on general surfaces. */
  moduleName: string | null;
  /** The module's id: a request typed here changes that module instead of making a new one. */
  appId?: string | null;
  moduleHint?: string | null;
}

/** The conversations to offer in the "Chat history" dropdown, newest first, with where each got
 * to as the visible secondary text. Scoped to the module's own thread when one is open. */
function useHistoryOptions(client: CoreClient, appId: string | null, refreshKey: string | null): StandardDropdownOption[] {
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [creations, setCreations] = useState<Map<string, Creation>>(new Map());

  useEffect(() => {
    let cancelled = false;
    const load = appId ? client.appConversations(appId) : client.listConversations();
    load
      .then((all) => {
        if (!cancelled) setItems(appId ? all : all.slice(0, 8));
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    if (!appId && isWorkflowsClient(client)) {
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
    // refreshKey (the selected conversation) changes on every new request, reply, or reset, so
    // a just-made or just-reopened conversation shows up without waiting for a remount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, appId, refreshKey]);

  return useMemo(() => {
    if (!items) return [];
    return items.map((c) => {
      const creation = creations.get(c.conversation_id);
      const where = appId
        ? `${c.change_of ? "Change" : "Made it"} · ${STATE_WORDS[c.state]}`
        : creation
          ? (CREATION_WORDS[creation.state] ?? creation.label)
          : STATE_WORDS[c.state];
      return { value: c.conversation_id, label: `${requestText(c) || "Untitled request"} — ${where}` };
    });
  }, [items, creations, appId]);
}

export function AssistantPanel({
  client,
  conversationId = null,
  onSelect,
  onOpenApp,
  context = { moduleName: null },
  headerStart,
  headerEnd,
  draft,
}: {
  client: CoreClient;
  conversationId?: string | null;
  onSelect?: (id: string | null) => void;
  onOpenApp?: (appId: string) => void;
  context?: AssistantContext;
  /** Reserved for the shell's own collapse toggle; the panel does not manage its own width. */
  headerStart?: ReactNode;
  /** Right slot of the header (the shell puts the Activity bell here). */
  headerEnd?: ReactNode;
  /** @deprecated the shell track owns collapse/hide now; pass a toggle via `headerStart` instead.
   * Kept optional so `App.tsx` (shell-owned) still type-checks until it is rewired. */
  onHide?: () => void;
  /** Text to start the composer with (for example from "Ask or change"). */
  draft?: string | null;
}) {
  const [ownSelection, setOwnSelection] = useState<string | null>(null);
  const selected = onSelect ? conversationId : ownSelection;
  const select = onSelect ?? setOwnSelection;
  const { conversation, loading, error, busy, reconnecting, start, reply, retry, cancel, reset } = useConversation(client, selected, select);
  const [text, setText] = useState("");
  const typedBefore = useRef("");
  const speech = useSpeech((final, interim) => setText(`${typedBefore.current} ${final} ${interim}`.replace(/\s+/g, " ").trim()));
  function toggleMic() {
    if (!speech.listening) typedBefore.current = text;
    speech.toggle();
  }
  const appId = context.appId ?? null;
  const historyOptions = useHistoryOptions(client, appId, selected);
  // Opened from a module, the panel is that module's thread: a conversation about something
  // else (or a new module made from Home) gives way to the module's own history.
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
  const made = creation?.state === "active";
  const making = creation !== null && !CREATION_DONE.has(creation.state);
  const thinking = conversation?.state === "thinking";

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const value = text.trim();
    if (!value || busy || thinking || making) return;
    const correctable = conversation && !made && (conversation.state === "briefed" || conversation.state === "answered" || conversation.state === "waiting_for_user");
    if (correctable) {
      await reply({ text: value });
    } else {
      if (conversation) reset();
      await start(value, appId);
    }
    setText("");
  }

  function startOver() {
    if (conversation) setText(requestText(conversation));
    reset();
  }

  const changing = conversation ? Boolean(conversation.change_of) : Boolean(appId);
  const contextLabel = conversation ? (changing ? "Changing a module" : "New module") : (context.moduleName ?? "Home");

  return (
    <aside className="assist" aria-label="Chief of Staff">
      <div className="assist__head">
        {headerStart}
        <div className="assist__title">
          <ZazooIcon size={32} />
          <div className="assist__titletext">
            <b>Chief of Staff</b>
            <div className="assist__ctx">{contextLabel}</div>
          </div>
        </div>
        {headerEnd ? <div className="assist__headend">{headerEnd}</div> : null}
      </div>
      <div className="assist__toolbar">
        <StandardDropdown options={historyOptions} value={selected} onChange={select} placeholder="Chat history" />
        <IconButton aria-label="New chat" onClick={reset}>
          <Plus size={16} />
        </IconButton>
      </div>
      <div className="assist__body">
        {!conversation ? (
          selected && loading ? (
            <p className="panel__hint" role="status">
              Opening your request…
            </p>
          ) : context.moduleName ? (
            <div className="msg msg--ai">
              I'm looking at <b>{context.moduleName}</b>. Describe what to change or add and Alpha rebuilds it in place. Everything already saved in it is
              kept.
              {context.moduleHint ? (
                <div className="faint" style={{ marginTop: 6 }}>
                  {context.moduleHint}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="assist-empty">
              Tell me what you want to keep track of, automate or get done…
              <div className="assist-empty__chips">
                {EXAMPLES.map((example) => (
                  <Button key={example} variant="outline" className="assist-empty__chip" onClick={() => setText(example)}>
                    {example}
                  </Button>
                ))}
              </div>
            </div>
          )
        ) : (
          <>
            {conversation.turns
              .filter((t) => t.role === "user")
              .map((t) => (
                <div key={t.turn_id} className="msg msg--user">
                  <Markdown text={turnText(t)} />
                </div>
              ))}
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
            {conversation.reply ? (
              <div className="msg msg--ai">
                <Markdown text={conversation.reply} />
              </div>
            ) : null}
            {thinking ? <Thinking since={conversation.updated_at} busy={busy} onStop={() => void cancel()} /> : null}
            {reconnecting ? (
              <p className="notice notice--quiet" role="status">
                Lost contact with Alpha's runtime for a moment. Reconnecting…
              </p>
            ) : null}
            {conversation.state === "failed" ? (
              <div className="failure" role="alert" aria-label="Alpha could not work this out">
                <p className="notice">Alpha could not work this out: {conversation.error ?? "something went wrong"}.</p>
                <div className="row">
                  <Button disabled={busy} onClick={() => void retry()}>
                    Try again
                  </Button>
                  <Button variant="outline" onClick={startOver}>
                    Start over
                  </Button>
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
                  <Button variant="outline" onClick={startOver}>
                    Describe another
                  </Button>
                </div>
              </div>
            ) : null}
            {making ? <p className="panel__hint">You can change the request once this attempt finishes, or after you stop it.</p> : null}
          </>
        )}
        {error ? (
          <p className="notice" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      <form className="composer" onSubmit={submit}>
        <div className="composer__box">
          <textarea
            id="goal"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask Chief of Staff… describe what you want done"
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
          <IconButton aria-label="Send" type="submit" disabled={busy || thinking || making || !text.trim()}>
            <ArrowUp size={16} />
          </IconButton>
        </div>
        <div className="composer__row">
          <span>{speech.error ?? "Uses your Claude subscription"}</span>
          <span style={{ marginLeft: "auto" }}>Enter to send · Shift+Enter for a new line</span>
        </div>
      </form>
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
        <Button size="sm" disabled={busy} onClick={onStop}>
          Stop
        </Button>
      </div>
    </div>
  );
}
