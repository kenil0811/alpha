import { useState, type FormEvent } from "react";
import { isWorkflowsClient, type CoreClient } from "../core/client";
import { CreationCard } from "../workflows/CreationCard";
import { BriefCard } from "./BriefCard";
import { QuestionsForm } from "./QuestionsForm";
import { useConversation } from "./useConversation";

const EXAMPLES = [
  "Track what I eat and how much, with calories, history and trends",
  "Turn my meeting notes into a one-page brief",
  "Keep a list of job openings I find and what I did about each",
];

export function AssistantPanel({ client, onOpenApp }: { client: CoreClient; onOpenApp?: (appId: string) => void }) {
  const { conversation, error, busy, start, reply, reset } = useConversation(client);
  const [text, setText] = useState("");
  const [correction, setCorrection] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    await start(text.trim());
    setText("");
  }

  const thinking = conversation?.state === "thinking";
  const userTurns = conversation?.turns.filter((t) => t.role === "user") ?? [];

  return (
    <section className="panel" aria-labelledby="assistant-heading">
      <h2 id="assistant-heading">Assistant</h2>
      {!conversation ? (
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
          {conversation.state === "failed" ? (
            <p className="notice" role="alert">
              Alpha could not work this out: {conversation.error ?? "unknown problem"}. Try again in a moment.
            </p>
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
                <button type="button" className="button" onClick={reset}>
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
