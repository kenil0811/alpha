// G1 primary use through an active App's own screen (F08.C01/C02), outside the native window.
//
// Loads the App's current sealed Version (data_dir/versions/<id>/dist/ui, with its CSP) in the
// pinned headless browser, in a frame sandboxed to scripts only, on a page that runs the same
// @alpha/ui-bridge host the shell uses with the same grant (the App's declared views and UI
// actions). Bridge requests go to the real Core with the shell's credential, exactly as the
// shell's appBridge does, so what the screen saves is the person's own data. Nothing here edits
// or bypasses the App; it only types and clicks like a person and takes screenshots.
//
// Usage: node evals/g1_screen.mjs <job.json>   (writes JSON lines; the last is the result)
//   job: {core_url, token, app_id, release_id, dist_dir, bridge_dir, browser, timezone, grant,
//         steps: [{kind: fill|select|check|click|press|wait_text|shot, label?, text?, key?}],
//         widths?: [1280, 768], evidence_dir, name}
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = dirname(dirname(fileURLToPath(import.meta.url)));
const { chromium } = await import(pathToFileURL(join(REPO, "workers/validator/node_modules/playwright-core/index.mjs")).href);

const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const HARNESS = "http://harness.alpha.invalid";
const APP = "http://app.alpha.invalid";
const out = (message) => process.stdout.write(JSON.stringify(message) + "\n");
const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const label = (text) => new RegExp(escape(text), "i");
const DONE = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

const state = { inflight: 0, lastActivity: Date.now(), openOps: new Set(), invokes: [], reads: 0, errors: [], blocked: [] };

async function core(path, init = {}) {
  const response = await fetch(`${job.core_url}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${job.token}`, "Content-Type": "application/json" },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? response.statusText;
    const code = { 400: "invalid_request", 403: "forbidden", 404: "not_found", 409: "invalid_request", 422: "invalid_request" }[response.status] ?? "internal";
    return { ok: false, error: { code, message } };
  }
  return { ok: true, result: body };
}

// The shell's appBridge and outcomeFromEvents, over HTTP.
async function relay(type, payload) {
  state.inflight += 1;
  state.lastActivity = Date.now();
  try {
    const app = encodeURIComponent(job.app_id);
    if (type === "records.query") {
      state.reads += 1;
      const { view, ...query } = payload;
      return await core(`/api/apps/${app}/views/${encodeURIComponent(view)}/query`, { method: "POST", body: JSON.stringify(query) });
    }
    if (type === "action.invoke") {
      const reply = await core(`/api/apps/${app}/actions/${encodeURIComponent(payload.action_id)}/runs`, {
        method: "POST",
        body: JSON.stringify({ input: payload.input, origin: "ui" }),
      });
      state.invokes.push({ action_id: payload.action_id, input: payload.input, ok: reply.ok, run_id: reply.result?.run_id ?? null });
      if (!reply.ok) return reply;
      state.openOps.add(reply.result.run_id);
      return { ok: true, result: { operation_id: reply.result.run_id } };
    }
    if (type === "operation.observe") {
      const id = payload.operation_id;
      const run = await core(`/api/runs/${encodeURIComponent(id)}`);
      if (!run.ok) return run;
      const r = run.result;
      if (!DONE.has(r.state)) return { ok: true, result: { operation_id: id, state: r.state, output: null, error: null } };
      state.openOps.delete(id);
      let error = null;
      if (r.state !== "succeeded") {
        const events = (await core(`/api/runs/${encodeURIComponent(id)}/events`)).result?.events ?? [];
        const worker = [...events].reverse().find((e) => e.kind === "worker.error")?.payload ?? {};
        const failed = [...events].reverse().find((e) => e.kind === "run.failed")?.payload ?? {};
        const message =
          (typeof worker.message === "string" && worker.message) ||
          (typeof failed.problem === "string" && `The result did not match what the action promises: ${failed.problem}`) ||
          r.terminal_reason ||
          `The action ${r.state}.`;
        error = { code: worker.operation_code || r.terminal_reason || r.state, message };
      }
      return { ok: true, result: { operation_id: id, state: r.state, output: r.output ?? null, error } };
    }
    return { ok: false, error: { code: "unsupported", message: `unsupported ${type}` } };
  } finally {
    state.inflight -= 1;
    state.lastActivity = Date.now();
  }
}

async function settle(page, limitMs = 120_000) {
  const start = Date.now();
  while (Date.now() - start < limitMs) {
    if (state.inflight === 0 && state.openOps.size === 0 && Date.now() - state.lastActivity > 700) {
      await page.waitForTimeout(200);
      if (state.inflight === 0 && state.openOps.size === 0) return true;
    }
    await page.waitForTimeout(100);
  }
  return false;
}

function harnessHtml() {
  const session = {
    session_id: `sess_g1_${Date.now().toString(16)}`,
    owner: { kind: "app", app_id: job.app_id, release_id: job.release_id },
    grant: job.grant,
    expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  };
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>g1</title>
<style>html,body{margin:0;padding:0;background:#fff}iframe{display:block;border:0;width:100%;height:100vh}</style></head>
<body><iframe id="app" title="App" sandbox="allow-scripts" src="${APP}/index.html"></iframe>
<script type="module">
import { BridgeHost, BridgeError } from "./bridge/index.js";
const session = ${JSON.stringify(session)};
const frame = document.getElementById("app");
const call = async (type, payload) => {
  const reply = await window.alphaRelay(type, payload);
  if (!reply.ok) throw new BridgeError(reply.error?.code ?? "internal", reply.error?.message ?? "failed");
  return reply.result;
};
let host = null;
window.addEventListener("message", (event) => {
  if (event.source !== frame.contentWindow) return;
  const data = event.data;
  if (!data || data.type !== "bridge.hello" || data.protocol_version !== "0.2") return;
  if (host) host.revoke("reconnected");
  host = new BridgeHost({ session, handlers: {
    recordsQuery: (_s, p) => call("records.query", p),
    actionInvoke: (_s, p) => call("action.invoke", p),
    operationObserve: (_s, p) => call("operation.observe", p),
  } });
  host.attachToWindow(frame.contentWindow);
  window.__alphaConnected = true;
});
</script></body></html>`;
}

async function routes(context) {
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === HARNESS) {
      if (url.pathname === "/" || url.pathname === "/index.html") return route.fulfill({ status: 200, contentType: "text/html", body: harnessHtml() });
      if (url.pathname.startsWith("/bridge/")) {
        const rel = normalize(url.pathname.slice("/bridge/".length));
        const file = [join(job.bridge_dir, rel), join(job.bridge_dir, `${rel}.js`)].find((f) => extname(f) === ".js" && existsSync(f));
        if (!rel.startsWith("..") && file) return route.fulfill({ status: 200, contentType: "text/javascript", body: readFileSync(file) });
      }
      if (url.pathname === "/favicon.ico") return route.fulfill({ status: 204, body: "" });
      return route.fulfill({ status: 404, body: "" });
    }
    if (url.origin === APP && url.pathname === "/index.html") {
      return route.fulfill({
        status: 200,
        contentType: "text/html",
        headers: { "content-security-policy": readFileSync(join(job.dist_dir, "index.csp"), "utf8") },
        body: readFileSync(join(job.dist_dir, "index.html")),
      });
    }
    state.blocked.push(url.href);
    return route.abort("blockedbyclient");
  });
}

const CONTROL_ROLES = { fill: ["textbox", "searchbox", "spinbutton", "combobox"], select: ["combobox", "listbox"], check: ["checkbox", "switch", "radio"] };
async function control(frame, kind, name) {
  for (const role of CONTROL_ROLES[kind]) {
    const exact = frame.getByRole(role, { name, exact: true });
    if ((await exact.count()) > 0) return exact.first();
  }
  for (const role of CONTROL_ROLES[kind]) {
    const loose = frame.getByRole(role, { name: label(name) });
    if ((await loose.count()) > 0) return loose.first();
  }
  return frame.getByRole(CONTROL_ROLES[kind][0], { name: label(name) }).first();
}
async function clickable(frame, name) {
  for (const role of ["button", "link", "tab", "menuitem", "option"]) {
    const found = frame.getByRole(role, { name: label(name) });
    if ((await found.count()) > 0) return found.first();
  }
  return frame.getByRole("button", { name: label(name) }).first();
}

async function shot(page, name) {
  mkdirSync(job.evidence_dir, { recursive: true });
  const frame = page.frames().find((f) => f.url().startsWith(APP));
  const height = frame ? await frame.evaluate(() => document.scrollingElement?.scrollHeight ?? 0).catch(() => 0) : 0;
  await page.evaluate((h) => (document.getElementById("app").style.height = `${h}px`), Math.min(Math.max(height, page.viewportSize().height), 4000));
  await page.waitForTimeout(100);
  const path = join(job.evidence_dir, `${job.name}-${name}.png`);
  await page.screenshot({ path, fullPage: true });
  await page.evaluate(() => (document.getElementById("app").style.height = "100vh"));
  return path;
}

const browser = await chromium.launch({ executablePath: job.browser, args: ["--disable-dev-shm-usage"] });
const result = { app_id: job.app_id, steps: [], screenshots: [], environment: { browser: browser.version(), node: process.version } };
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1, locale: "en-US", timezoneId: job.timezone });
  await context.exposeFunction("alphaRelay", relay);
  await routes(context);
  const page = await context.newPage();
  page.on("console", (m) => m.type() === "error" && state.errors.push(m.text().slice(0, 300)));
  page.on("pageerror", (e) => state.errors.push(String(e).slice(0, 300)));
  await page.goto(`${HARNESS}/index.html`);
  await page.waitForFunction(() => window.__alphaConnected === true, null, { timeout: 20_000 });
  const frame = page.frameLocator("#app");
  await frame.getByText("Connecting to Alpha").waitFor({ state: "detached", timeout: 15_000 }).catch(() => undefined);
  await settle(page);
  result.screenshots.push(await shot(page, "opened"));
  for (const [index, step] of (job.steps ?? []).entries()) {
    const started = Date.now();
    const entry = { index, step, ok: true };
    try {
      if (step.kind === "fill") await (await control(frame, "fill", step.label)).fill(step.text, { timeout: 8_000 });
      else if (step.kind === "select") await (await control(frame, "select", step.label)).selectOption({ label: step.text }, { timeout: 8_000 });
      else if (step.kind === "check") await (await control(frame, "check", step.label)).check({ timeout: 8_000 });
      else if (step.kind === "click") await (await clickable(frame, step.label)).click({ timeout: 8_000 });
      else if (step.kind === "press") await page.keyboard.press(step.key);
      else if (step.kind === "wait_text") await frame.getByText(label(step.text)).first().waitFor({ state: "visible", timeout: step.timeout_ms ?? 120_000 });
      else if (step.kind === "shot") entry.screenshot = await shot(page, step.text);
      entry.settled = await settle(page);
    } catch (error) {
      entry.ok = false;
      entry.error = String(error?.message ?? error).split("\n")[0].slice(0, 400);
    }
    entry.ms = Date.now() - started;
    result.steps.push(entry);
    out({ kind: "step", ...entry });
    if (!entry.ok) break;
  }
  for (const width of job.widths ?? [1280, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(300);
    const appFrame = page.frames().find((f) => f.url().startsWith(APP));
    const size = await appFrame.evaluate(() => ({ scroll_width: document.scrollingElement.scrollWidth, client_width: document.scrollingElement.clientWidth }));
    result[`layout_${width}`] = size;
    result.screenshots.push(await shot(page, `final-${width}`));
  }
  result.text = (await page.frames().find((f) => f.url().startsWith(APP)).evaluate(() => document.body.innerText)).slice(0, 4000);
} catch (error) {
  result.error = String(error?.stack ?? error).slice(0, 2000);
} finally {
  await browser.close();
}
result.invokes = state.invokes;
result.reads = state.reads;
result.console_errors = state.errors.slice(0, 20);
result.blocked = state.blocked.slice(0, 20);
result.ok = !result.error && result.steps.every((s) => s.ok);
out({ kind: "result", ...result });
