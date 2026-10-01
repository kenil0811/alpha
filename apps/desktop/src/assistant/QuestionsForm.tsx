import { useState, type FormEvent } from "react";
import type { OpenQuestion } from "../core/client";
import { Button } from "../ui";

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
  // Every question takes several picks (a person can hold more than one role, want several
  // outcomes, use many tools) plus their own words; the answer joins them with "; ".
  const [choices, setChoices] = useState<Record<string, string[]>>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const toggle = (id: string, option: string) =>
    setChoices((c) => {
      const picked = c[id] ?? [];
      return { ...c, [id]: picked.includes(option) ? picked.filter((o) => o !== option) : [...picked, option] };
    });

  function submit(event: FormEvent) {
    event.preventDefault();
    const answers: Record<string, string> = {};
    for (const q of questions) {
      const parts = [...(choices[q.id] ?? []), (other[q.id] ?? "").trim()].filter(Boolean);
      if (parts.length) answers[q.id] = parts.join("; ");
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
              <input type="checkbox" name={q.id} value={option} checked={(choices[q.id] ?? []).includes(option)} onChange={() => toggle(q.id, option)} />
              {option}
            </label>
          ))}
          <label className="question__option">
            Something else:
            <input type="text" aria-label={`Your own answer for: ${q.question}`} value={other[q.id] ?? ""} onChange={(e) => setOther((o) => ({ ...o, [q.id]: e.target.value }))} />
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
