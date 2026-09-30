/**
 * Shown instead of a plain reply when a model call itself failed (Core sends `model_error` on
 * the turn - see `alpha.assistant.acting.model_error_kind`): one line naming what's not
 * connected, then the one action that actually gets past it. Shared by the Chief of Staff panel
 * and the floating avatar.
 */
import { useState } from "react";
import { hasTauri } from "../core/session";
import { isModelAccountsClient, type CoreClient, type ModelErrorInfo } from "../core/client";

const PROVIDER_LABEL: Record<string, string> = {
  claude: "Claude",
  chatgpt: "ChatGPT",
  openrouter: "OpenRouter",
  grok: "Grok",
};

const PROVIDER_SIGN_IN: Record<string, { which: string; hint: string }> = {
  claude: { which: "claude", hint: "Run `claude` in a terminal, then choose /login." },
  chatgpt: { which: "codex", hint: "Run `codex login` in a terminal." },
};

/** `client` is whatever the surface already has (CoreClient or ActClient); only the model-account
 *  methods are used, and only when the runtime actually offers them. */
export function NotConnectedCard({ info, client, onResend }: { info: ModelErrorInfo; client: unknown; onResend: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const label = PROVIDER_LABEL[info.provider] ?? info.provider;
  const accounts = isModelAccountsClient(client) ? client : null;

  async function recheck() {
    if (!accounts) return;
    setBusy(true);
    try {
      const providers = await accounts.listModelAccounts();
      const mine = providers.find((p) => p.id === info.provider);
      if (mine?.dot.color === "green") {
        onResend();
      } else {
        setNote(mine ? mine.dot.tooltip : "Still not connected.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function saveKey() {
    if (!accounts || !key.trim()) return;
    setBusy(true);
    try {
      const updated = await accounts.saveModelKey(info.provider, key.trim());
      setKey("");
      if (updated.dot.color === "green") onResend();
      else setNote(updated.dot.tooltip);
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const signIn = PROVIDER_SIGN_IN[info.provider];

  return (
    <div className="msg msg--ai notconnected" role="alert">
      <b>Not connected to {label}.</b>
      {note ? <div className="faint">{note}</div> : null}
      {info.kind === "sign_in" ? (
        <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          {hasTauri() && signIn ? (
            <button
              type="button"
              className="btn btn--sm btn--primary"
              disabled={busy}
              onClick={() => {
                void import("@tauri-apps/api/core").then(({ invoke }) => invoke("open_terminal_sign_in", { which: signIn.which }));
              }}
            >
              Open Terminal to sign in
            </button>
          ) : signIn ? (
            <span className="faint">{signIn.hint}</span>
          ) : null}
          <button type="button" className="btn btn--sm" disabled={busy || !accounts} onClick={() => void recheck()}>
            I've signed in
          </button>
        </div>
      ) : info.kind === "key" ? (
        <div className="row" style={{ gap: 6, marginTop: 8, alignItems: "center" }}>
          <input
            type="password"
            placeholder="Paste a key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            style={{ width: 160 }}
            aria-label={`${label} key`}
          />
          <button type="button" className="btn btn--sm btn--primary" disabled={busy || !key.trim() || !accounts} onClick={() => void saveKey()}>
            Save
          </button>
        </div>
      ) : (
        <div className="row" style={{ gap: 6, marginTop: 8 }}>
          <button type="button" className="btn btn--sm" disabled={busy} onClick={onResend}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

/** Read a session/act turn's `model_error` out of its loosely-typed `detail`, if any. */
export function modelErrorOf(detail: Record<string, unknown> | null | undefined): ModelErrorInfo | null {
  const raw = detail?.model_error as Partial<ModelErrorInfo> | undefined;
  if (!raw || typeof raw.provider !== "string") return null;
  const kind = raw.kind === "sign_in" || raw.kind === "key" ? raw.kind : "generic";
  return { kind, provider: raw.provider };
}

export type { CoreClient };
