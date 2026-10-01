/**
 * One conversation as a card inside a session: how Alpha understood the request, its questions
 * or proposed shapes, the brief, and the creation that follows. Core owns the conversation and
 * the creation, so the card shows the same state wherever it is opened from.
 */
import { useCallback, useEffect, useState } from "react";
import { CREATION_DONE, isWorkflowsClient, type Conversation, type CoreClient, type Creation, type Proposal } from "../core/client";
import { CreationCard } from "../workflows/CreationCard";
import { BriefCard } from "./BriefCard";
import { QuestionsForm, useAnswers } from "./QuestionsForm";
import { useConversation } from "./useConversation";

export const STATE_WORDS: Record<Conversation["state"], string> = {
  thinking: "Thinking",
  researching: "Looking around",
  proposed: "Options to choose from",
  waiting_for_user: "Waiting for your answers",
  briefed: "Planned",
  answered: "Answered",
  failed: "Didn't work out",
};

export function requestText(conversation: Conversation): string {
  const first = conversation.turns.find((t) => t.role === "user");
  return String(first?.content.text ?? "");
}

export function ConversationCard({
  client,
  conversationId,
  onOpenApp,
  onStartOver,
  onCreation,
  showRequest = false,
}: {
  client: CoreClient;
  conversationId: string;
  onOpenApp?: (appId: string) => void;
  /** The person wants to say it again: the request text goes back to the composer. */
  onStartOver?: (text: string) => void;
  onCreation?: (creation: Creation | null) => void;
  /** Show the request itself at the top (when the card stands alone, outside a session). */
  showRequest?: boolean;
}) {
  const noSelect = useCallback(() => undefined, []);
  const { conversation, loading, error, busy, reconnecting, reply, retry, cancel } = useConversation(client, conversationId, noSelect);
  const [creation, setCreation] = useState<Creation | null>(null);
  const creationChanged = useCallback(
    (c: Creation | null) => {
      setCreation(c);
      onCreation?.(c);
    },
    [onCreation],
  );
  useEffect(() => setCreation(null), [conversationId]);

  if (!conversation) {
    return loading ? (
      <p className="panel__hint" role="status">
        Opening your request…
      </p>
    ) : null;
  }
  const thinking = conversation.state === "thinking" || conversation.state === "researching";
  const researching = conversation.state === "researching";
  const made = creation?.state === "active";
  const making = creation !== null && !CREATION_DONE.has(creation.state);
  const changing = Boolean(conversation.change_of);

  return (
    <div className="convo" aria-label={changing ? "Changing a project" : "New project"}>
      <div className="convo__label">{changing ? "Changing a project" : "New project"}</div>
      {showRequest ? <div className="msg msg--user">{requestText(conversation)}</div> : null}
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
      {thinking ? <Thinking since={conversation.updated_at} busy={busy} onStop={() => void cancel()} label={researching ? "Looking around before proposing a shape…" : undefined} /> : null}
      {reconnecting ? (
        <p className="notice notice--quiet" role="status">
          Lost contact with Alpha's runtime for a moment. Reconnecting…
        </p>
      ) : null}
      {conversation.state === "failed" ? (
        <div className="failure" role="alert" aria-label="Alpha could not work this out">
          <p className="notice">Alpha could not work this out: {conversation.error ?? "something went wrong"}.</p>
          <div className="row">
            <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void retry()}>
              Try again
            </button>
            {onStartOver ? (
              <button type="button" className="btn" onClick={() => onStartOver(requestText(conversation))}>
                Start over
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {conversation.state === "waiting_for_user" && conversation.questions.length ? (
        <QuestionsForm questions={conversation.questions} busy={busy} onAnswer={(answers) => reply({ answers })} onDefaults={() => reply({ use_defaults: true })} />
      ) : null}
      {conversation.state === "proposed" && conversation.proposal ? <ProposalCard proposal={conversation.proposal} busy={busy} onChoose={(option, answers) => reply({ text: `Go with "${option.title}": ${option.summary}`, ...(Object.keys(answers).length ? { answers } : {}) })} /> : null}
      {conversation.current_brief && !thinking && conversation.state !== "proposed" ? <BriefCard brief={conversation.current_brief} dataNotice={conversation.data_notice} /> : null}
      {conversation.state === "briefed" && conversation.delivery === "app" && (conversation.current_brief || conversation.quick_change) && isWorkflowsClient(client) ? (
        <CreationCard
          client={client}
          conversationId={conversation.conversation_id}
          briefRevision={conversation.quick_change ? 0 : (conversation.current_brief?.revision ?? 0)}
          unavailable={conversation.current_brief?.unavailable_capabilities ?? []}
          auto={changing}
          onOpen={(appId) => onOpenApp?.(appId)}
          onChange={creationChanged}
        />
      ) : null}
      {made ? (
        <div className="after-made" aria-label="After it was made">
          <p className="panel__hint">
            {creation?.change_of
              ? `${creation?.result?.name ?? creation?.app_name ?? "Your project"} is updated and its data is kept. To change it again, just say so here.`
              : `${creation?.result?.name ?? creation?.app_name ?? "Your project"} is in the sidebar. To change it later, open it and describe the change here.`}
          </p>
        </div>
      ) : null}
      {making ? <p className="panel__hint">You can change the request once this attempt finishes, or after you stop it.</p> : null}
      {!made && !making && conversation.state === "briefed" && !changing ? <p className="panel__hint">To change or add something before it is made, just say so below.</p> : null}
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Two or three shapes Alpha proposes after looking around; the person picks one. */
function ProposalCard({ proposal, busy, onChoose }: { proposal: Proposal; busy: boolean; onChoose: (option: Proposal["options"][number], answers: Record<string, string>) => void }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const decisions = useAnswers(proposal.questions ?? []);
  return (
    <div className="card card--pad proposal" aria-label="Options">
      <p style={{ marginTop: 0 }}>{proposal.intro}</p>
      {proposal.findings?.length ? (
        <ul className="proposal__findings" aria-label="What Alpha found">
          {proposal.findings.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      ) : null}
      {proposal.questions?.length ? <div className="questions">{decisions.fields}</div> : null}
      <div className="proposal__options">
        {proposal.options.map((option) => (
          <div key={option.id} className={`proposal__option${option.id === proposal.default ? " proposal__option--default" : ""}`}>
            <b>
              {option.title}
              {option.id === proposal.default ? <span className="pill pill--info" style={{ marginLeft: 8 }}>Alpha's pick</span> : null}
            </b>
            <p>{option.summary}</p>
            <p className="faint">{option.why}</p>
            <button type="button" className={`btn btn--sm${option.id === proposal.default ? " btn--primary" : ""}`} disabled={busy} onClick={() => onChoose(option, decisions.answers())}>
              {option.id === proposal.default ? "Go with this" : "Go with this instead"}
            </button>
          </div>
        ))}
      </div>
      {proposal.evidence.length ? (
        <p className="faint" style={{ marginBottom: 0 }}>
          <button type="button" className="btn btn--sm btn--ghost" onClick={() => setShowEvidence((v) => !v)} aria-expanded={showEvidence}>
            {showEvidence ? "Hide what Alpha looked at" : `What Alpha looked at (${proposal.evidence.length})`}
          </button>
        </p>
      ) : null}
      {showEvidence ? (
        <ul className="proposal__evidence">
          {proposal.evidence.map((e, i) => (
            <li key={i}>
              <a href={e.url} target="_blank" rel="noreferrer">
                {e.title}
              </a>
              <span className="faint"> · {e.note}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** The wait, made visible: how long it has been, a word when it is longer than usual, and Stop. */
export function Thinking({ since, busy, onStop, label }: { since: string; busy?: boolean; onStop?: () => void; label?: string }) {
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
        {label ?? "Thinking about your request…"} <span className="faint">{clock}</span>
      </div>
      {seconds >= 90 ? <div className="faint" style={{ marginTop: 4 }}>Longer than usual. A large request or a busy model service can take a few minutes; you can stop and try again.</div> : null}
      {onStop ? (
        <div className="row" style={{ marginTop: 8 }}>
          <button type="button" className="btn btn--sm" disabled={busy} onClick={onStop}>
            Stop
          </button>
        </div>
      ) : null}
    </div>
  );
}
