/**
 * Minimal "generated" React UI used to qualify the unprivileged surface (F03).
 * It only knows the bridge. Everything else it tries below is expected to fail.
 */
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BridgeClient, BridgeRequestError } from "@alpha/ui-bridge";

type Probe = { name: string; expect: string; observed: string; pass: boolean };

async function runProbes(): Promise<Probe[]> {
  const out: Probe[] = [];
  const w = window as unknown as Record<string, unknown>;
  const add = (name: string, expect: string, observed: string, pass: boolean) => out.push({ name, expect, observed, pass });
  add("__TAURI_INTERNALS__", "undefined", typeof w.__TAURI_INTERNALS__, typeof w.__TAURI_INTERNALS__ === "undefined");
  add("__TAURI__", "undefined", typeof w.__TAURI__, typeof w.__TAURI__ === "undefined");
  try {
    const doc = (window.parent as unknown as { document: unknown }).document;
    add("parent.document", "throws SecurityError", `readable (${typeof doc})`, false);
  } catch (e) {
    add("parent.document", "throws SecurityError", String(e).slice(0, 80), true);
  }
  try {
    const t = (window.parent as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    add("parent.__TAURI_INTERNALS__", "throws SecurityError", `readable (${typeof t})`, false);
  } catch (e) {
    add("parent.__TAURI_INTERNALS__", "throws SecurityError", String(e).slice(0, 80), true);
  }
  for (const url of ["ipc://localhost/plugin:app|version", "http://ipc.localhost/plugin:app|version", "http://127.0.0.1:49165/api/health", "https://example.com/"]) {
    try {
      const r = await fetch(url, { method: "GET" });
      add(`fetch ${url}`, "rejected", `status ${r.status}`, false);
    } catch (e) {
      add(`fetch ${url}`, "rejected", String(e).slice(0, 80), true);
    }
  }
  try {
    const ws = new WebSocket("ws://127.0.0.1:49165/");
    ws.close();
    add("WebSocket to loopback", "throws", "constructed", false);
  } catch (e) {
    add("WebSocket to loopback", "throws", String(e).slice(0, 80), true);
  }
  try {
    window.localStorage.setItem("x", "1");
    add("localStorage", "throws SecurityError", "writable", false);
  } catch (e) {
    add("localStorage", "throws SecurityError", String(e).slice(0, 80), true);
  }
  const popup = window.open("https://example.com/", "_blank");
  add("window.open", "null (blocked)", popup === null ? "null" : "opened", popup === null);
  const before = window.location.href;
  try {
    (window.top as Window).location.href = "https://example.com/";
    await new Promise((r) => setTimeout(r, 300));
    add("top.location navigation", "blocked", window.location.href === before ? "unchanged" : "navigated", window.location.href === before);
  } catch (e) {
    add("top.location navigation", "blocked", String(e).slice(0, 80), true);
  }
  const form = document.createElement("form");
  form.action = "https://example.com/submit";
  form.method = "post";
  document.body.appendChild(form);
  form.submit();
  await new Promise((r) => setTimeout(r, 300));
  add("form.submit()", "blocked (no allow-forms)", window.location.href === before ? "no navigation" : "navigated", window.location.href === before);
  form.remove();
  try {
    const remote = "https://example.com/x.js";
    await import(/* @vite-ignore */ remote);
    add("dynamic import from network", "rejected", "loaded", false);
  } catch (e) {
    add("dynamic import from network", "rejected", String(e).slice(0, 80), true);
  }
  add("document.cookie", "empty", JSON.stringify(document.cookie), document.cookie === "");
  add("origin", "null (opaque)", window.origin, window.origin === "null");
  return out;
}

function App() {
  const [client, setClient] = useState<BridgeClient | null>(null);
  const [status, setStatus] = useState("connecting to host…");
  const [text, setText] = useState("hello from generated ui");
  const [operation, setOperation] = useState<string>("");
  const [foreign, setForeign] = useState<string>("");
  const [log, setLog] = useState<string[]>([]);
  const [probes, setProbes] = useState<Probe[] | null>(null);
  const push = (line: string) => setLog((l) => [line, ...l].slice(0, 12));

  useEffect(() => {
    BridgeClient.connect({ timeoutMs: 15_000 })
      .then((c) => {
        setClient(c);
        setStatus(`session ${c.sessionId} · actions ${JSON.stringify(c.grant?.actions)} · views ${JSON.stringify(c.grant?.read_views)}`);
        c.onRevoked((reason) => setStatus(`REVOKED: ${reason}`));
      })
      .catch((e) => setStatus(`no host: ${String(e)}`));
  }, []);

  async function call(type: Parameters<BridgeClient["request"]>[0], payload: Record<string, unknown>) {
    if (!client) return;
    try {
      const result = await client.request(type, payload, 15_000);
      push(`${type} → ok ${JSON.stringify(result).slice(0, 120)}`);
      return result as Record<string, unknown>;
    } catch (e) {
      const err = e as BridgeRequestError;
      push(`${type} → ${err.code}: ${err.message}`);
      return null;
    }
  }

  return (
    <div style={{ fontFamily: "sans-serif", fontSize: 13, padding: 12, color: "#eee", background: "#202329" }}>
      <div data-testid="status" style={{ marginBottom: 8 }}>{status}</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        <input aria-label="Text" value={text} onChange={(e) => setText(e.target.value)} />
        <button
          onClick={async () => {
            const r = await call("action.invoke", { action_id: "synthetic.echo", input: { text } });
            if (r && typeof r.operation_id === "string") setOperation(r.operation_id);
          }}
        >
          Invoke synthetic.echo
        </button>
        <button disabled={!operation} onClick={() => call("operation.observe", { operation_id: operation })}>
          Observe my operation
        </button>
        <input aria-label="Foreign operation id" placeholder="other session's operation id" value={foreign} onChange={(e) => setForeign(e.target.value)} />
        <button disabled={!foreign} onClick={() => call("operation.observe", { operation_id: foreign })}>
          Observe foreign
        </button>
        <button onClick={() => call("operation.observe", { operation_id: "run_not_created_by_this_session" })}>
          Observe not mine
        </button>
        <button onClick={() => call("records.query", { view: "anything" })}>records.query</button>
        <button onClick={() => call("shell.navigate", { destination: "settings" })}>shell.navigate</button>
        <button onClick={() => runProbes().then(setProbes)}>Run isolation probes</button>
      </div>
      <ol data-testid="log" style={{ margin: 0, paddingLeft: 18 }}>
        {log.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ol>
      {probes ? (
        <div data-testid="probe-summary" style={{ marginTop: 8, fontWeight: 600 }}>
          probes: {probes.filter((p) => p.pass).length}/{probes.length} pass
          {probes.some((p) => !p.pass) ? ` · FAIL: ${probes.filter((p) => !p.pass).map((p) => p.name).join(", ")}` : ""}
        </div>
      ) : null}
      {probes ? (
        <table data-testid="probes" style={{ marginTop: 8, borderCollapse: "collapse", width: "100%" }}>
          <tbody>
            {probes.map((p) => (
              <tr key={p.name} style={{ color: p.pass ? "#7be08a" : "#ff8080" }}>
                <td style={{ padding: "1px 6px" }}>{p.pass ? "PASS" : "FAIL"}</td>
                <td style={{ padding: "1px 6px" }}>{p.name}</td>
                <td style={{ padding: "1px 6px", opacity: 0.8 }}>{p.observed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
