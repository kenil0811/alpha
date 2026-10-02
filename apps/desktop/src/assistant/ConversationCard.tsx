/**
 * One conversation as a card: only the questions, the proposed options and where it stands,
 * then the creation that follows. The plan itself lives elsewhere (the project page's Plan
 * section); off a project page it sits behind "See plan". Core owns the conversation and the
 * creation, so the card shows the same state wherever it is opened from.
 */
import { useCallback, useEffect, useState } from "react";
import { CREATION_DONE, isWorkflowsClient, type Conversation, type CoreClient, type Creation, type Proposal } from "../core/client";
import { CreationCard } from "../workflows/CreationCard";
import { InfoTip } from "../ui";
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

/** The step a conversation is on, in a few words: the card's one progress line. */
export function stepOf(state: Conversation["state"], creation: Creation | null): string | null {
  if (state === "briefed" && creation?.state === "active") return "Done";
  if (state === "briefed" && creation && !CREATION_DONE.has(creation.state)) return "Building";
  const steps: Partial<Record<Conversation["state"], string>> = {
    thinking: "Understanding your request",
    researching: "Looking around",
    proposed: "Options ready",
    waiting_for_user: "Waiting for your answers",
    briefed: "Planned",
  };
  return steps[state] ?? null;
}

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
  onPage = false,
}: {
  client: CoreClient;
  conversationId: string;
  onOpenApp?: (appId: string) => void;
  /** The person wants to say it again: the request text goes back to the composer. */
  onStartOver?: (text: string) => void;
  onCreation?: (creation: Creation | null) => void;
  /** Show the request itself at the top (when the card stands alone, outside a session). */
  showRequest?: boolean;
  /** On the project's own page, which shows the plan in its own section. */
  onPage?: boolean;
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
  const made = creation?.state === "active";
  const making = creation !== null && !CREATION_DONE.has(creation.state);
  const changing = Boolean(conversation.change_of);
  const step = stepOf(conversation.state, creation);
  const hint = making
    ? "You can change the request once this attempt finishes, or after you stop it."
    : !made && conversation.state === "briefed" && !changing
      ? "To change or add something before it is made, just say so in the chat."
      : null;

  return (
    <div className={onPage ? "convo convo--page" : "convo"} aria-label={changing ? "Changing a project" : "New project"}>
      {!thinking && (step || !onPage) ? (
        <div className="convo__step">
          <span className="convo__steptext">{[onPage ? null : changing ? "Changing a project" : "New project", step].filter(Boolean).join(" · ")}</span>
          {hint ? <InfoTip content={hint} label="How to change it" /> : null}
        </div>
      ) : null}
      {showRequest ? <div className="msg msg--user">{requestText(conversation)}</div> : null}
      {conversation.state === "answered" && conversation.reply ? <div className="msg msg--ai">{conversation.reply}</div> : null}
      {thinking ? <Thinking since={conversation.updated_at} busy={busy} onStop={() => void cancel()} label={`${step}…`} /> : null}
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
      {conversation.state === "briefed" && conversation.current_brief ? (
        onPage ? (
          <p className="convo__plan">Plan ready — see Plan below</p>
        ) : (
          <details className="convo__plan">
            <summary>See plan</summary>
            <BriefCard brief={conversation.current_brief} dataNotice={conversation.data_notice} />
          </details>
        )
      ) : null}
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
          <p className="panel__hint row" style={{ gap: 4, alignItems: "center", flexWrap: "nowrap", minWidth: 0 }}>
            <span className="truncate">
              {creation?.result?.name ?? creation?.app_name ?? "Your project"} is {creation?.change_of ? "updated" : "ready"}.
            </span>
            <InfoTip
              content={creation?.change_of ? "Its data is kept. To change it again, just say so here." : "It's in the sidebar. To change it later, open it and describe the change here."}
              label="How to change it later"
            />
          </p>
        </div>
      ) : null}
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** The chat's pointer to a creation card shown on the project page: only once there is
 *  something there to look at (questions, options or a plan), not while Alpha is still
 *  thinking. */
export function PagePointer({ client, conversationId }: { client: CoreClient; conversationId: string }) {
  const noSelect = useCallback(() => undefined, []);
  const { conversation } = useConversation(client, conversationId, noSelect);
  const state = conversation?.state;
  if (state !== "waiting_for_user" && state !== "proposed" && state !== "briefed") return null;
  return <div className="msg msg--ai convo__pointer">{state === "briefed" ? "The plan is on the page." : "Questions and options are on the page."}</div>;
}

/** Two or three shapes Alpha proposes after looking around; the person picks one. */
function ProposalCard({ proposal, busy, onChoose }: { proposal: Proposal; busy: boolean; onChoose: (option: Proposal["options"][number], answers: Record<string, string>) => void }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const decisions = useAnswers(proposal.questions ?? []);
  return (
    <div className="card card--pad proposal" aria-label="Options">
      <p className="proposal__intro" title={proposal.intro}>{proposal.intro}</p>
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
