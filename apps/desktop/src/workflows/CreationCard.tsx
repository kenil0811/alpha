/**
 * Creating a result (UX §4): progress in the person's words, a specific next step when it does
 * not work out, and a final card saying what works and how to start. Preview images are the
 * checks' own screenshots with sample data, labelled as such; nothing here is the person's data.
 */
import { useEffect, useRef, useState } from "react";
import type { Creation, WorkflowsClient } from "../core/client";
import { useCreation } from "./useCreation";

const STAGES: { key: string; label: string }[] = [
  { key: "planning", label: "Deciding how to check it" },
  { key: "building", label: "Building it" },
  { key: "checking", label: "Checking that it works" },
  { key: "active", label: "Ready to use" },
];

const PREVIEW_LABELS: Record<string, string> = {
  "primary-1280": "After adding something",
  "populated-1280": "With several entries",
  "populated-768": "In a narrow window",
  "error-save": "When saving fails",
};

function stageIndex(state: string): number {
  if (state === "activating") return 3;
  const index = STAGES.findIndex((s) => s.key === state);
  return index === -1 ? 0 : index;
}

export function CreationCard({
  client,
  conversationId,
  briefRevision,
  unavailable,
  onOpen,
  onChange,
  auto = false,
}: {
  client: WorkflowsClient;
  conversationId: string;
  briefRevision: number;
  unavailable: string[];
  onOpen: (appId: string) => void;
  /** Tells the surrounding conversation where the creation stands. */
  onChange?: (creation: Creation | null) => void;
  /** A change the person already asked for: it starts on its own, no second approval. */
  auto?: boolean;
}) {
  const { creation, loaded, error, busy, reconnecting, refresh, start, cancel } = useCreation(client, conversationId, briefRevision);
  useEffect(() => {
    if (loaded) onChange?.(creation);
  }, [loaded, creation, onChange]);
  const autoStarted = useRef<string | null>(null);
  useEffect(() => {
    if (!auto || !loaded || creation || busy || autoStarted.current === `${conversationId}:${briefRevision}`) return;
    autoStarted.current = `${conversationId}:${briefRevision}`;
    void start();
  }, [auto, loaded, creation, busy, start, conversationId, briefRevision]);

  if (!loaded) {
    return (
      <p className="panel__hint" role="status">
        Checking whether this is already being made…
      </p>
    );
  }

  if (!creation && auto && !error) {
    return (
      <p className="panel__hint" role="status">
        Starting the change…
      </p>
    );
  }

  if (!creation || creation.state === "cancelled") {
    return (
      <div className="creation" aria-label="Create it">
        <p className="panel__hint">
          {creation?.state === "cancelled"
            ? "Stopped. Nothing was switched on."
            : "When the plan above looks right, Alpha builds it, checks it and switches it on for you."}
        </p>
        <div className="row">
          <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void start()}>
            {creation?.state === "cancelled" ? "Create it again" : "Create it"}
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

  if (creation.state === "active" && creation.result) {
    return <ReadyCard client={client} name={creation.result.name ?? creation.app_name ?? "Your App"} creation={creation} unavailable={unavailable} onOpen={onOpen} />;
  }

  if (creation.state === "failed") {
    const failure = creation.failure;
    return (
      <div className="creation creation--failed" aria-label="Not made">
        <p className="notice" role="alert">
          {failure?.message ?? "It could not be made."}
        </p>
        {failure?.failed_checks?.length ? (
          <details>
            <summary>What the checks found</summary>
            <ul>
              {failure.failed_checks.map((check) => (
                <li key={check}>{check}</li>
              ))}
            </ul>
          </details>
        ) : null}
        <p className="panel__hint">
          {failure?.next_step === "revise"
            ? "Try changing or narrowing the request below, then create it again."
            : "You can try again; nothing was switched on."}
        </p>
        <div className="row">
          <button type="button" className="button button--primary" disabled={busy} onClick={() => void start()}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  const current = stageIndex(creation.state);
  return (
    <div className="creation" aria-label="Creating it" aria-busy="true">
      <ol className="stages">
        {STAGES.map((stage, index) => (
          <li key={stage.key} className={index < current ? "stages__done" : index === current ? "stages__current" : "stages__next"}>
            <span aria-hidden="true">{index < current ? "✓" : index === current ? "…" : "·"}</span> {stage.label}
            {index < current ? <span className="sr-only"> (done)</span> : index === current ? <span className="sr-only"> (in progress)</span> : null}
          </li>
        ))}
      </ol>
      <p role="status" className="panel__hint">
        {creation.label}
        {creation.detail ? ` · ${creation.detail}` : ""}
        {creation.progress.checks_run ? ` · ${creation.progress.checks_run} checks so far` : ""}
      </p>
      {reconnecting ? (
        <p className="notice notice--quiet" role="status">
          Lost contact with Alpha's runtime for a moment. The work carries on; reconnecting…
        </p>
      ) : null}
      <p className="panel__hint">
        This usually takes several minutes. You can use other parts of Alpha meanwhile; this request stays under Recent
        requests.
      </p>
      <div className="row">
        {creation.state === "activating" ? (
          <span className="panel__hint">Switching it on now; this can no longer be stopped.</span>
        ) : (
          <button type="button" className="button" onClick={() => void cancel()}>
            Stop
          </button>
        )}
        {reconnecting ? (
          <button type="button" className="button" onClick={refresh}>
            Check now
          </button>
        ) : null}
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ReadyCard({
  client,
  name,
  creation,
  unavailable,
  onOpen,
}: {
  client: WorkflowsClient;
  name: string;
  creation: NonNullable<ReturnType<typeof useCreation>["creation"]>;
  unavailable: string[];
  onOpen: (appId: string) => void;
}) {
  const result = creation.result!;
  const [images, setImages] = useState<{ name: string; src: string }[]>([]);
  useEffect(() => {
    let cancelled = false;
    const urls: string[] = [];
    Promise.all(
      result.preview_images.map(async (image) => {
        const src = await client.imageUrl(image.url);
        urls.push(src);
        return { name: image.name, src };
      }),
    )
      .then((loaded) => {
        if (!cancelled) setImages(loaded);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [client, result.preview_images]);

  const verb = creation.change_of ? "is updated" : "is ready";
  return (
    <div className="creation creation--ready" aria-label={`${name} ${verb}`}>
      <h3 className="creation__title">
        {name} {verb}
      </h3>
      <p>
        It passed all {result.checks_passed} of its checks
        {result.attempts > 1 ? ` (it took ${result.attempts} tries)` : ""}.{" "}
        {creation.change_of ? "Its data is kept. " : ""}
        {result.has_ui ? "Open it to use its screen." : "Open it to run it from Alpha."}
      </p>
      {unavailable.length ? (
        <p className="panel__hint">Not connected yet, so not part of it: {unavailable.join(", ")}.</p>
      ) : null}
      <div className="row">
        <button type="button" className="button button--primary" onClick={() => onOpen(result.app_id)}>
          Open {name}
        </button>
      </div>
      {images.length ? (
        <figure className="preview">
          <figcaption>
            <span className="preview__label">Preview</span> What Alpha's checks saw, using sample data. Your own list starts empty.
          </figcaption>
          <div className="preview__images">
            {images.map((image) => (
              <img key={image.name} src={image.src} alt={`Preview: ${PREVIEW_LABELS[image.name] ?? image.name}`} title={PREVIEW_LABELS[image.name]} />
            ))}
          </div>
        </figure>
      ) : null}
    </div>
  );
}
