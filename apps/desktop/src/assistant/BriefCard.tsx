import type { SolutionBrief } from "@alpha/contracts";
import { briefKeeps, capabilityLabel, deliveryLabel } from "./plain";

export function BriefCard({ brief, dataNotice }: { brief: SolutionBrief; dataNotice?: string | null }) {
  const keeps = briefKeeps(brief);
  return (
    <section className="brief" aria-label="What Alpha understood">
      <h3 className="brief__title">What Alpha will make: {deliveryLabel(brief.delivery)}</h3>
      <p className="brief__goal">{brief.goal}</p>
      <p className="panel__hint">{brief.success_summary}</p>
      {brief.primary_journey.length ? (
        <div className="brief__section">
          <h4>How you'll use it</h4>
          <ol>
            {brief.primary_journey.map((step, i) => (
              <li key={i}>
                <strong>{step.action}</strong> — {step.expected_result}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {keeps.length ? (
        <div className="brief__section">
          <h4>What it keeps for you</h4>
          <ul>
            {keeps.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {brief.assumptions.length ? (
        <div className="brief__section">
          <h4>Assumptions you can change</h4>
          <ul>
            {brief.assumptions.map((a, i) => (
              <li key={i}>
                {a.text}{" "}
                <span className="brief__tag">{a.source === "model_default" ? "default" : a.source === "user_answer" ? "you chose" : "you corrected"}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {brief.unavailable_capabilities.length ? (
        <div className="brief__section brief__section--limit">
          <h4>Not possible yet</h4>
          <ul>
            {brief.unavailable_capabilities.map((c) => (
              <li key={c}>{capabilityLabel(c)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {dataNotice ? (
        <p className="brief__notice">
          <strong>Where your data goes:</strong> {dataNotice}
        </p>
      ) : null}
      <div className="brief__meta">Understanding {brief.revision}</div>
    </section>
  );
}
