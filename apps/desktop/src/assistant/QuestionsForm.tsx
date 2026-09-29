import { useState, type FormEvent } from "react";
import type { OpenQuestion } from "../core/client";
import { Button } from "../ui";

const OTHER = "__other__";

export function QuestionsForm({
  questions,
  busy,
  onAnswer,
  onDefaults,
}: {
  questions: OpenQuestion[];
  busy: boolean;
  onAnswer: (answers: Record<string, string>) => void;
  onDefaults: () => void;
}) {
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [other, setOther] = useState<Record<string, string>>({});

  function submit(event: FormEvent) {
    event.preventDefault();
    const answers: Record<string, string> = {};
    for (const q of questions) {
      const choice = choices[q.id];
      const text = (other[q.id] ?? "").trim();
      if (choice && choice !== OTHER) answers[q.id] = choice;
      else if (text) answers[q.id] = text;
    }
    if (Object.keys(answers).length === 0) return;
    onAnswer(answers);
  }

  return (
    <form className="questions" onSubmit={submit} aria-label="A few questions">
      {questions.map((q) => (
        <fieldset key={q.id} className="question">
          <legend>{q.question}</legend>
          <p className="panel__hint">{q.why_it_matters}</p>
          {q.options.map((option) => (
            <label key={option} className="question__option">
              <input
                type="radio"
                name={q.id}
                value={option}
                checked={choices[q.id] === option}
                onChange={() => setChoices((c) => ({ ...c, [q.id]: option }))}
              />
              {option}
            </label>
          ))}
          <label className="question__option">
            <input
              type="radio"
              name={q.id}
              value={OTHER}
              checked={choices[q.id] === OTHER}
              onChange={() => setChoices((c) => ({ ...c, [q.id]: OTHER }))}
            />
            Something else:
            <input
              type="text"
              aria-label={`Your own answer for: ${q.question}`}
              value={other[q.id] ?? ""}
              onFocus={() => setChoices((c) => ({ ...c, [q.id]: OTHER }))}
              onChange={(e) => setOther((o) => ({ ...o, [q.id]: e.target.value }))}
            />
          </label>
        </fieldset>
      ))}
      <div className="row">
        <Button type="submit" disabled={busy}>
          Continue
        </Button>
        <Button type="button" variant="outline" disabled={busy} onClick={onDefaults}>
          Use these defaults for now
        </Button>
      </div>
    </form>
  );
}
