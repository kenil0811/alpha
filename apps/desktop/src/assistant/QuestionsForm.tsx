import { useState, type FormEvent } from "react";
import type { OpenQuestion } from "../core/client";
import { Button } from "../ui";

/** Every question takes several picks (a person can hold more than one role, want several
 *  outcomes, use many tools) plus their own words; an answer joins them with "; ". Shared by
 *  the first questions and the decisions asked alongside the options. */
export function useAnswers(questions: OpenQuestion[]) {
  const [choices, setChoices] = useState<Record<string, string[]>>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const toggle = (id: string, option: string) =>
    setChoices((c) => {
      const picked = c[id] ?? [];
      return { ...c, [id]: picked.includes(option) ? picked.filter((o) => o !== option) : [...picked, option] };
    });
  function answers(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const q of questions) {
      const parts = [...(choices[q.id] ?? []), (other[q.id] ?? "").trim()].filter(Boolean);
      if (parts.length) out[q.id] = parts.join("; ");
    }
    return out;
  }
  const fields = questions.map((q) => (
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
  ));
  return { fields, answers };
}

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
  const { fields, answers } = useAnswers(questions);

  function submit(event: FormEvent) {
    event.preventDefault();
    const picked = answers();
    if (Object.keys(picked).length === 0) return;
    onAnswer(picked);
  }

  return (
    <form className="questions" onSubmit={submit} aria-label="A few questions">
      {fields}
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
