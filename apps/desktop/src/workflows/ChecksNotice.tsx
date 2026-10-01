/**
 * The fast lane's follow-up: a simple module is switched on after its structural checks, and
 * its behaviour checks run right after. This tells the person where those stand and, when
 * they find a problem, offers one click back: the previous version for a change, or taking
 * a new module out of use. Nothing is deleted either way.
 */
import { useState } from "react";
import type { CreationChecks, WorkflowsClient } from "../core/client";

const NOT_RUN: Record<string, string> = {
  plan_unavailable: "Alpha couldn't write them",
  restarted: "Alpha restarted meanwhile",
  lost: "Alpha restarted meanwhile",
};

export function ChecksNotice({
  checks,
  client,
  appId,
  changeOf,
  releaseId,
  onReverted,
  onRemoved,
}: {
  checks: CreationChecks;
  client: Pick<WorkflowsClient, "revertApp" | "removeApp">;
  appId: string;
  /** Set when the module existed before: the way back is its previous version. */
  changeOf?: string | null;
  /** The release the checks belong to; the way back is refused if it changed since. */
  releaseId?: string | null;
  onReverted?: () => void;
  onRemoved?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [kept, setKept] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (checks.status === "pending") {
    return (
      <p className="panel__hint" role="status">
        It is switched on already. Alpha is still checking how it behaves; you can use it meanwhile.
      </p>
    );
  }
  if (checks.status === "passed") {
    return (
      <p className="notice notice--ok" role="status">
        Its behaviour checks passed{checks.checks_passed ? ` (${checks.checks_passed} checks)` : ""}.
      </p>
    );
  }
  if (checks.status === "preliminary") {
    const counted = checks.checks_passed ? ` (${checks.checks_passed} checks)` : "";
    return (
      <p className={checks.full === "pending" ? "panel__hint" : "notice notice--quiet"} role="status">
        It was checked only against the examples in your request{counted}, because Alpha's full checks were not ready in time.{" "}
        {checks.full === "pending"
          ? "The full checks are being written again and will run shortly; you can use it meanwhile."
          : "Alpha couldn't write its full checks. It stays switched on; tell Alpha if something is off."}
      </p>
    );
  }
  if (checks.status === "not_run") {
    return (
      <p className="notice notice--quiet" role="status">
        Its behaviour checks did not run ({NOT_RUN[checks.reason ?? ""] ?? "they were interrupted"}). It stays switched on; tell Alpha if something is off.
      </p>
    );
  }
  if (done) {
    return (
      <p className="panel__hint" role="status">
        {done}
      </p>
    );
  }
  if (kept) return null;

  const failed = checks.failed_checks ?? [];
  const back = async () => {
    setBusy(true);
    setError(null);
    try {
      if (changeOf) {
        await client.revertApp(appId, releaseId ?? null);
        setDone("Back on the previous version. Your records are kept.");
        onReverted?.();
      } else {
        await client.removeApp(appId, releaseId ?? null);
        setDone("Taken out of use. Nothing was deleted; ask Alpha to make it again when you like.");
        onRemoved?.();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack" style={{ gap: 6 }} aria-label="Checks found a problem">
      <p className="notice" role="alert">
        Alpha's later checks found a problem{failed.length ? `: ${failed[0]}` : ""}.
      </p>
      {failed.length > 1 ? (
        <details>
          <summary>Everything the checks found</summary>
          <ul>
            {failed.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </details>
      ) : null}
      <div className="row">
        <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => void back()}>
          {changeOf ? "Go back to the previous version" : "Remove it"}
        </button>
        <button type="button" className="btn btn--sm" disabled={busy} onClick={() => setKept(true)}>
          Keep it anyway
        </button>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
