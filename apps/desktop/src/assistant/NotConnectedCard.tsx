/**
 * Shown instead of a plain reply when a model call itself failed (Core sends `model_error` on
 * the turn - see `alpha.assistant.acting.model_error_kind`): one line naming what's not
 * connected, then the one action that actually gets past it. Shared by the Chief of Staff panel
 * and the floating avatar.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { isModelAccountsClient, type CoreClient, type ModelErrorInfo } from "../core/client";

const PROVIDER_LABEL: Record<string, string> = {
  claude: "Claude",
  chatgpt: "ChatGPT",
  openrouter: "OpenRouter",
  grok: "Grok",
};

/** Providers that sign in through their CLI in the browser (Core runs `claude auth login` /
 *  `codex login`); the rest connect with a key. */
const BROWSER_SIGN_IN = new Set(["claude", "chatgpt"]);
const POLL_MS = 3000;
const GIVE_UP_MS = 5 * 60 * 1000;

/** `client` is whatever the surface already has (CoreClient or ActClient); only the model-account
 *  methods are used, and only when the runtime actually offers them. `auto` (the newest turn
 *  only) opens the browser sign-in straight away, so an older card in the history never does. */
export function NotConnectedCard({ info, client, onResend, auto = false }: { info: ModelErrorInfo; client: unknown; onResend: () => void; auto?: boolean }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  // Claude's sign-in page shows a code to paste back here (Bridge's flow); ChatGPT's CLI finishes
  // by itself, so that one is polled instead.
  const [needsCode, setNeedsCode] = useState(false);
  const [code, setCode] = useState("");
  const [note, setNote] = useState<string | null>(null);
  // ChatGPT without Codex on this Mac: Install Codex first (Core links or installs it, never a
  // terminal), then Connect.
  const [install, setInstall] = useState<"needed" | "running" | null>(null);
  const label = PROVIDER_LABEL[info.provider] ?? info.provider;
  const accounts = isModelAccountsClient(client) ? client : null;
  const browser = info.kind === "sign_in" && BROWSER_SIGN_IN.has(info.provider);
  const resend = useRef(onResend);
  resend.current = onResend;

  /** True (and the message resent) once Core sees the provider connected. */
  const connected = useCallback(async () => {
    if (!accounts) return false;
    const mine = (await accounts.listModelAccounts()).find((p) => p.id === info.provider);
    if (mine?.dot.color === "green") {
      resend.current();
      return true;
    }
    setNote(mine?.dot.tooltip ?? "Still not connected.");
    return false;
  }, [accounts, info.provider]);

  const signIn = useCallback(async () => {
    if (!accounts) return;
    setNote(null);
    try {
      const started = await accounts.signInModelAccount(info.provider);
      if (started.needs_code) setNeedsCode(true);
      else setWaiting(true);
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    }
  }, [accounts, info.provider]);

  useEffect(() => {
    if (!browser || !accounts) return;
    let live = true;
    const check = info.provider === "chatgpt" ? accounts.listModelAccounts().then((all) => all.find((p) => p.id === info.provider)?.state === "cli_missing") : Promise.resolve(false);
    void check
      .catch(() => false)
      .then((missing) => {
        if (!live) return;
        if (missing) setInstall("needed");
        else if (auto) void signIn();
      });
    return () => {
      live = false;
    };
  }, [auto, browser, accounts, info.provider, signIn]);

  // While Codex installs in the background, check every few seconds until it lands.
  useEffect(() => {
    if (install !== "running" || !accounts) return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      void accounts
        .listModelAccounts()
        .then((all) => {
          const row = all.find((p) => p.id === info.provider);
          if (row?.installing && Date.now() - started < GIVE_UP_MS) return;
          if (row?.state === "cli_missing") {
            setInstall("needed");
            setNote("Codex didn't install. Try again, or add a ChatGPT API key in Settings.");
          } else setInstall(null);
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [install, accounts, info.provider]);

  async function installCli() {
    if (!accounts) return;
    setBusy(true);
    setNote(null);
    try {
      const row = await accounts.installModelCli(info.provider);
      setInstall(row.installing ? "running" : row.state === "cli_missing" ? "needed" : null);
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // While the browser sign-in is open, check every few seconds and resend once it lands.
  useEffect(() => {
    if (!waiting) return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (Date.now() - started > GIVE_UP_MS) {
        setWaiting(false);
        setNote("Sign-in didn't finish. Try again when you're ready.");
        return;
      }
      void connected()
        .then((ok) => ok && setWaiting(false))
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting, connected]);

  async function recheck() {
    setBusy(true);
    try {
      if (await connected()) setWaiting(false);
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function connectCode() {
    if (!accounts || !code.trim()) return;
    setBusy(true);
    try {
      const updated = await accounts.finishModelSignIn(info.provider, code.trim());
      setCode("");
      if (updated.dot.color === "green") {
        setNeedsCode(false);
        onResend();
      } else setNote(updated.dot.tooltip);
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
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

  return (
    <div className="msg msg--ai notconnected" role="alert">
      <b>Not connected to {label}.</b>
      {waiting || needsCode ? (
        <div className="faint" role="status">
          {needsCode ? "Approve in your browser, then paste the code it shows." : "Finish signing in in your browser. Alpha carries on by itself."}
        </div>
      ) : null}
      {note ? <div className="faint">{note}</div> : null}
      {browser && needsCode ? (
        <div className="row" style={{ gap: 6, marginTop: 8, alignItems: "center", flexWrap: "nowrap" }}>
          <input
            placeholder="Paste the code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void connectCode()}
            style={{ flex: "1 1 120px", minWidth: 0, maxWidth: 220 }}
            aria-label={`${label} sign-in code`}
          />
          <button type="button" className="btn btn--sm btn--primary" disabled={busy || !code.trim()} onClick={() => void connectCode()}>
            Connect
          </button>
        </div>
      ) : null}
      {browser && install ? (
        <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn btn--sm btn--primary" disabled={busy || install === "running"} onClick={() => void installCli()}>
            {install === "running" ? "Installing Codex…" : "Install Codex"}
          </button>
        </div>
      ) : browser ? (
        <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn btn--sm btn--primary" disabled={busy || !accounts} onClick={() => void signIn()}>
            {waiting || needsCode ? "Open sign-in again" : info.provider === "chatgpt" ? `Connect ${label}` : `Sign in to ${label}`}
          </button>
          <button type="button" className="btn btn--sm" disabled={busy || !accounts} onClick={() => void recheck()}>
            I've signed in
          </button>
        </div>
      ) : info.kind === "key" ? (
        <div className="row" style={{ gap: 6, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="password"
            placeholder="Paste a key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            style={{ flex: "1 1 120px", minWidth: 0, maxWidth: 220 }}
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
