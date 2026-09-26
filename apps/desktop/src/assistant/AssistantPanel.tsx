import { useEffect, useState, type FormEvent } from "react";
import { CREATION_DONE, isWorkflowsClient, type Conversation, type CoreClient, type Creation } from "../core/client";
import { CreationCard } from "../workflows/CreationCard";
import { BriefCard } from "./BriefCard";
import { QuestionsForm } from "./QuestionsForm";
import { useConversation } from "./useConversation";

const EXAMPLES = [
  "Track what I eat and how much, with calories, history and trends",
  "Turn my meeting notes into a one-page brief",
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

export function AssistantPanel({
  client,
  conversationId = null,
  onSelect,
  onOpenApp,
}: {
  client: CoreClient;
  conversationId?: string | null;
  onSelect?: (id: string | null) => void;
  onOpenApp?: (appId: string) => void;
}) {
  // Standalone use (tests, fixtures) keeps its own selection; the shell passes its own.
  const [ownSelection, setOwnSelection] = useState<string | null>(null);
  const selected = onSelect ? conversationId : ownSelection;
  const select = onSelect ?? setOwnSelection;
  const { conversation, loading, error, busy, reconnecting, start, reply, retry, reset } = useConversation(client, selected, select);
  const [text, setText] = useState("");
  const [correction, setCorrection] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    await start(text.trim());
    setText("");
  }

  function startOver() {
    if (conversation) setText(requestText(conversation));
    reset();
  }

  const thinking = conversation?.state === "thinking";
  const userTurns = conversation?.turns.filter((t) => t.role === "user") ?? [];

  return (
    <section className="panel surface surface--reading" aria-labelledby="assistant-heading">
      <div className="surface__head">
        <h2 id="assistant-heading">Assistant</h2>
        {conversation ? (
          <button type="button" className="button" onClick={reset}>
            New request
          </button>
        ) : null}
      </div>
      {!conversation ? (
        selected && loading ? (
          <p className="panel__hint" role="status">
            Opening your request…
          </p>
        ) : (
          <>
            <form onSubmit={submit}>
              <div className="field">
                <label htmlFor="goal">What do you want done?</label>
                <textarea
                  id="goal"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Describe the outcome in your own words"
                  autoFocus
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") e.currentTarget.form?.requestSubmit();
                  }}
                />
              </div>
              <div className="row" style={{ marginTop: "var(--space-3)" }}>
                <button type="submit" className="button button--primary" disabled={busy || !text.trim()}>
                  Ask Alpha
                </button>
              </div>
              <div className="examples">
                <span className="panel__hint">For example:</span>
                {EXAMPLES.map((example) => (
                  <button key={example} type="button" className="example" onClick={() => setText(example)}>
                    {example}
                  </button>
                ))}
              </div>
            </form>
            <RecentRequests client={client} onOpen={select} />
          </>
        )
      ) : (
        <div className="thread">
          {userTurns.length ? (
            <div className="bubble bubble--user">
              <div className="bubble__label">You asked</div>
              {String(userTurns[0].content.text ?? "")}
            </div>
          ) : null}
          {conversation.interpretation ? (
            <div className="interpretation" aria-label="How Alpha understood it">
              <div className="bubble__label">How Alpha understood it</div>
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
          {conversation.reply ? <div className="bubble bubble--assistant">{conversation.reply}</div> : null}
          {thinking ? (
            <div className="bubble bubble--assistant" role="status">
              Thinking about your request…
            </div>
          ) : null}
          {reconnecting ? (
            <p className="notice notice--quiet" role="status">
              Lost contact with Alpha's runtime for a moment. Reconnecting…
            </p>
          ) : null}
          {conversation.state === "failed" ? (
            <div className="failure" role="alert" aria-label="Alpha could not work this out">
              <p className="notice">Alpha could not work this out: {conversation.error ?? "something went wrong"}.</p>
              <div className="row">
                <button type="button" className="button button--primary" disabled={busy} onClick={() => void retry()}>
                  Try again
                </button>
                <button type="button" className="button" onClick={startOver}>
                  Start over
                </button>
              </div>
            </div>
          ) : null}
          {conversation.state === "waiting_for_user" && conversation.questions.length ? (
            <QuestionsForm
              questions={conversation.questions}
              busy={busy}
              onAnswer={(answers) => reply({ answers })}
              onDefaults={() => reply({ use_defaults: true })}
            />
          ) : null}
          {conversation.current_brief && conversation.state !== "thinking" ? <BriefCard brief={conversation.current_brief} /> : null}
          {conversation.state === "briefed" &&
          conversation.delivery === "app" &&
          conversation.current_brief &&
          isWorkflowsClient(client) ? (
            <CreationCard
              client={client}
              conversationId={conversation.conversation_id}
              briefRevision={conversation.current_brief.revision}
              unavailable={conversation.current_brief.unavailable_capabilities}
              onOpen={(appId) => onOpenApp?.(appId)}
            />
          ) : null}
          {conversation.state === "briefed" || conversation.state === "answered" || conversation.state === "waiting_for_user" ? (
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
                <input
                  id="correction"
                  value={correction}
                  onChange={(e) => setCorrection(e.target.value)}
                  placeholder="e.g. also track protein"
                />
              </div>
              <div className="row">
                <button type="submit" className="button" disabled={busy || !correction.trim()}>
                  Send
                </button>
                <button type="button" className="button" onClick={startOver}>
                  Start over
                </button>
              </div>
            </form>
          ) : null}
        </div>
      )}
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
    </section>
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
