// Trusted UI render check for an App candidate (F07). Launched by Core as a supervised worker.
//
// stdin line 1: the job. Afterwards stdin carries Core's replies; stdout carries JSON lines:
//   {"kind":"bridge","id":n,"type":"records.query"|"action.invoke"|"operation.observe","payload":{}}
//   {"kind":"control","id":n,"op":"seed"|"saved"|"count","collection"?}
//   {"kind":"check", ...CheckResult}      one result per check, as it happens
//   {"kind":"result","output":{...}}      environment, then exit
//
// The candidate's sealed static UI loads in a sandboxed frame (scripts only, opaque origin) on a
// harness page that runs the real @alpha/ui-bridge host from the UI build profile. Nothing is
// served over a network: Playwright answers the two virtual origins from disk. The frame's bridge
// requests reach Core only through this process, and only for the session's grant.
import { chromium } from "playwright-core";
import { mkdirSync, readFileSync, existsSync } from "node:fs";
import { createInterface } from "node:readline";
import { extname, join, normalize } from "node:path";

const HARNESS = "http://harness.alpha.invalid";
const APP = "http://app.alpha.invalid";
const out = (message) => process.stdout.write(JSON.stringify(message) + "\n");

const pending = new Map();
let nextId = 1;
let job = null;
const lines = createInterface({ input: process.stdin });
lines.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  if (job === null) {
    job = message;
    main().then(
      () => process.exit(0),
      (error) => {
        out({ kind: "error", code: "validator_crashed", message: String(error?.stack ?? error).slice(0, 2000) });
        process.exit(3);
      },
    );
    return;
  }
  const resolve = pending.get(message.id);
  if (resolve) {
    pending.delete(message.id);
    resolve(message);
  }
});
const ask = (message) =>
  new Promise((resolve) => {
    const id = nextId++;
    pending.set(id, resolve);
    out({ ...message, id });
  });

const checks = [];
function check(id, status, summary, detail = {}, evidence = [], required = true) {
  const result = { id, stage: "ui", required, status, summary: String(summary).slice(0, 1000), detail, evidence };
  checks.push(result);
  out({ kind: "check", ...result });
  return status === "passed";
}
const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const label = (text) => new RegExp(escape(text), "i");

// ---------------------------------------------------------------- relay state
const state = { inflight: 0, lastActivity: Date.now(), openOps: new Set(), invokes: 0, opStates: {}, faults: { records: false, action: false } };
const errors = [];

async function relay(type, payload) {
  state.inflight += 1;
  state.lastActivity = Date.now();
  try {
    if (type === "records.query" && state.faults.records) {
      return { ok: false, error: { code: "internal", message: "Alpha could not read the saved data right now." } };
    }
    if (type === "action.invoke") {
      state.invokes += 1;
      if (state.faults.action) {
        return { ok: false, error: { code: "internal", message: "Alpha could not save this right now." } };
      }
    }
    const reply = await ask({ kind: "bridge", type, payload });
    if (reply.ok && type === "action.invoke" && reply.result?.operation_id) state.openOps.add(reply.result.operation_id);
    if (reply.ok && type === "operation.observe") {
      const op = reply.result?.operation_id;
      const opState = reply.result?.state;
      if (op && ["succeeded", "failed", "cancelled", "interrupted"].includes(opState)) {
        state.openOps.delete(op);
        state.opStates[op] = opState;
      }
    }
    return reply.ok ? { ok: true, result: reply.result } : { ok: false, error: reply.error };
  } finally {
    state.inflight -= 1;
    state.lastActivity = Date.now();
  }
}

async function settle(page, limitMs = 20_000) {
  const start = Date.now();
  while (Date.now() - start < limitMs) {
    const quiet = Date.now() - state.lastActivity > 500;
    if (state.inflight === 0 && state.openOps.size === 0 && quiet) {
      await page.waitForTimeout(150);
      if (state.inflight === 0 && state.openOps.size === 0) return true;
    }
    await page.waitForTimeout(100);
  }
  return false;
}

// ---------------------------------------------------------------- pages
function harnessHtml() {
  const session = {
    session_id: `sess_validator_${Date.now().toString(16)}`,
    owner: { kind: "app", app_id: job.app_id, release_id: "preview" },
    grant: job.grant,
    expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  };
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>validator</title>
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
  const distDir = job.dist_dir;
  const bridgeDir = job.bridge_dir;
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === HARNESS) {
      if (url.pathname === "/" || url.pathname === "/index.html") {
        return route.fulfill({ status: 200, contentType: "text/html", body: harnessHtml() });
      }
      if (url.pathname.startsWith("/bridge/")) {
        // The packed bridge is compiled for bundlers: its relative imports omit ".js".
        const rel = normalize(url.pathname.slice("/bridge/".length));
        const file = [join(bridgeDir, rel), join(bridgeDir, `${rel}.js`)].find((f) => extname(f) === ".js" && existsSync(f));
        if (!rel.startsWith("..") && file) {
          return route.fulfill({ status: 200, contentType: "text/javascript", body: readFileSync(file) });
        }
      }
      if (url.pathname === "/favicon.ico") return route.fulfill({ status: 204, body: "" });
      return route.fulfill({ status: 404, body: "" });
    }
    if (url.origin === APP && url.pathname === "/index.html") {
      return route.fulfill({
        status: 200,
        contentType: "text/html",
        headers: { "content-security-policy": readFileSync(join(distDir, "index.csp"), "utf8") },
        body: readFileSync(join(distDir, "index.html")),
      });
    }
    state.blocked = [...(state.blocked ?? []), url.href].slice(-20);
    return route.abort("blockedbyclient");
  });
}

const appFrame = (page) => page.frames().find((f) => f.url().startsWith(APP));

async function open(page) {
  await page.goto(`${HARNESS}/index.html`);
  await page.waitForFunction(() => window.__alphaConnected === true, null, { timeout: 15_000 });
  await settle(page);
  const frame = page.frameLocator("#app");
  // The kit shows "Connecting to Alpha…" until the session is up.
  await frame.getByText("Connecting to Alpha").waitFor({ state: "detached", timeout: 10_000 }).catch(() => undefined);
  await settle(page);
  return frame;
}

async function screenshot(page, name) {
  mkdirSync(job.evidence_dir, { recursive: true });
  const frame = appFrame(page);
  const height = frame ? await frame.evaluate(() => document.scrollingElement?.scrollHeight ?? 0).catch(() => 0) : 0;
  const viewport = page.viewportSize();
  await page.evaluate((h) => {
    document.getElementById("app").style.height = `${h}px`;
  }, Math.min(Math.max(height, viewport.height), 4000));
  await page.waitForTimeout(100);
  const path = join(job.evidence_dir, `${name}.png`);
  await page.screenshot({ path, fullPage: true });
  await page.evaluate(() => {
    document.getElementById("app").style.height = "100vh";
  });
  return `${job.evidence_ref}/${name}.png`;
}

async function layout(page, width, name) {
  await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(250);
  const frame = appFrame(page);
  const size = await frame.evaluate(() => {
    const el = document.scrollingElement ?? document.documentElement;
    return { scroll_width: el.scrollWidth, client_width: el.clientWidth };
  });
  const evidence = [await screenshot(page, `${name}-${width}`)];
  const blocking = size.scroll_width > size.client_width + 1;
  if (blocking) {
    // The frame clips what overflows; widen it once so the screenshot shows the overflow.
    await page.evaluate((w) => {
      document.getElementById("app").style.width = `${w}px`;
    }, size.scroll_width);
    evidence.push(await screenshot(page, `${name}-${width}-overflow`));
    await page.evaluate(() => {
      document.getElementById("app").style.width = "100%";
    });
  }
  check(
    `ui.${name}.layout_${width}`,
    blocking ? "failed" : "passed",
    blocking
      ? `at ${width}px the screen is ${size.scroll_width}px wide and scrolls sideways (blocking overflow)`
      : `no sideways scrolling at ${width}px`,
    size,
    evidence,
  );
  await page.setViewportSize({ width: 1280, height: 900 });
}

async function visible(frame, text) {
  const locator = frame.getByText(label(text));
  const count = await locator.count();
  for (let i = 0; i < Math.min(count, 20); i += 1) {
    if (await locator.nth(i).isVisible()) return true;
  }
  return false;
}

async function alertShown(frame) {
  const alerts = frame.getByRole("alert");
  const count = await alerts.count();
  for (let i = 0; i < count; i += 1) {
    const item = alerts.nth(i);
    if ((await item.isVisible()) && (await item.innerText()).trim()) return (await item.innerText()).trim().slice(0, 300);
  }
  return null;
}

// A plan names fields the way a person sees them. Look only at controls of the right kind, so a
// section or card whose title happens to contain the same words is never mistaken for the field.
const CONTROL_ROLES = {
  fill: ["textbox", "searchbox", "spinbutton", "combobox"],
  select: ["combobox", "listbox"],
  check: ["checkbox", "switch", "radio"],
};

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

async function perform(page, frame, steps) {
  for (const [index, step] of steps.entries()) {
    try {
      if (step.kind === "fill") await (await control(frame, "fill", step.label)).fill(step.text, { timeout: 5_000 });
      else if (step.kind === "select") await (await control(frame, "select", step.label)).selectOption({ label: step.text }, { timeout: 5_000 });
      else if (step.kind === "check") await (await control(frame, "check", step.label)).check({ timeout: 5_000 });
      else if (step.kind === "click") await (await clickable(frame, step.label)).click({ timeout: 5_000 });
      else if (step.kind === "press") await page.keyboard.press(step.key);
    } catch (error) {
      const what = step.label ? `${step.kind} "${step.label}"` : `${step.kind} ${step.key ?? ""}`;
      return { ok: false, step: index, message: `step ${index + 1} (${what}) could not be done: ${String(error?.message ?? error).split("\n")[0].slice(0, 300)}` };
    }
  }
  return { ok: true };
}

function errorsSince(mark) {
  return errors.slice(mark);
}

function cleanCheck(id, mark, what) {
  const found = errorsSince(mark);
  return check(
    id,
    found.length ? "failed" : "passed",
    found.length ? `${what}: the screen logged ${found.length} error(s): ${found[0]}` : `${what}: no script errors`,
    { errors: found.slice(0, 10) },
  );
}

// ---------------------------------------------------------------- phases
async function main() {
  const browser = await chromium.launch({ executablePath: job.browser, args: ["--disable-dev-shm-usage"] });
  const environment = { browser: browser.version(), playwright: job.playwright_version ?? "", node: process.version };
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1, locale: "en-US", timezoneId: job.timezone });
    await routes(context);
    const page = await context.newPage();
    // Only the harness page may call the relay; the sandboxed App frame cannot reach it.
    await page.exposeBinding("alphaRelay", (source, type, payload) => {
      if (source.frame !== page.mainFrame()) return { ok: false, error: { code: "forbidden", message: "not the host" } };
      return relay(type, payload);
    });
    page.on("pageerror", (error) => errors.push(`uncaught: ${String(error?.message ?? error).slice(0, 300)}`));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(`console: ${message.text().slice(0, 300)}`);
    });

    // 1. Empty state.
    let mark = errors.length;
    let frame;
    try {
      frame = await open(page);
    } catch (error) {
      check("ui.empty.render", "failed", `the screen did not connect to Alpha: ${String(error?.message ?? error).split("\n")[0]}`, { errors: errors.slice(0, 5) }, [await screenshot(page, "empty-failed")]);
      return;
    }
    const title = frame.locator("h1").first();
    const hasTitle = (await title.count()) > 0 && (await title.isVisible());
    const evidence = [await screenshot(page, "empty-1280")];
    check("ui.empty.render", hasTitle ? "passed" : "failed", hasTitle ? `rendered "${(await title.innerText()).slice(0, 80)}"` : "the screen rendered no page title (h1)", {}, evidence);
    const emptyAlert = await alertShown(frame);
    check("ui.empty.no_error", emptyAlert ? "failed" : "passed", emptyAlert ? `with no saved data the screen shows an error: ${emptyAlert}` : "no error shown when nothing is saved yet");
    cleanCheck("ui.empty.clean", mark, "empty state");
    await layout(page, 768, "empty");

    // 2. Primary interaction.
    const plan = job.plan;
    if (!plan) {
      check("ui.primary.steps", "skipped", "the validation plan has no UI interaction; a screen cannot be verified without one");
    } else {
      mark = errors.length;
      const invokesBefore = state.invokes;
      const done = await perform(page, frame, plan.primary);
      await settle(page);
      check("ui.primary.steps", done.ok ? "passed" : "failed", done.ok ? `performed ${plan.primary.length} step(s)` : done.message, { steps: plan.primary }, [await screenshot(page, "primary-1280")]);
      if (done.ok) {
        const invoked = state.invokes - invokesBefore;
        if (plan.saved) {
          check("ui.primary.action", invoked > 0 ? "passed" : "failed", invoked > 0 ? `the screen invoked ${invoked} declared action(s)` : "the screen did not invoke any declared action; nothing it shows as saved can be stored");
        }
        const outcomes = Object.values(state.opStates);
        const failedOps = outcomes.filter((s) => s !== "succeeded");
        check("ui.primary.outcome", failedOps.length ? "failed" : "passed", failedOps.length ? `${failedOps.length} action(s) the screen started did not succeed` : "every action the screen started succeeded", { states: state.opStates });
        if (plan.saved) {
          const saved = await ask({ kind: "control", op: "saved" });
          check("ui.primary.saved", saved.result?.status === "passed" ? "passed" : "failed", saved.result?.summary ?? "no answer", saved.result?.detail ?? {});
        }
        for (const text of plan.shows ?? []) {
          const seen = await visible(frame, text);
          check(`ui.primary.shows.${plan.shows.indexOf(text) + 1}`, seen ? "passed" : "failed", seen ? `shows "${text}" after the interaction` : `"${text}" is not visible after the interaction`);
        }
        cleanCheck("ui.primary.clean", mark, "primary interaction");
      }
    }

    // 3. Populated state (data created through the App's own actions).
    if (plan && (plan.seed?.length || plan.seed_shows?.length)) {
      mark = errors.length;
      const seeded = await ask({ kind: "control", op: "seed" });
      const seededOk = seeded.result?.ok === true;
      check("ui.populated.seed", seededOk ? "passed" : "failed", seededOk ? `created sample data with ${plan.seed.length} action run(s)` : `sample data could not be created: ${seeded.result?.summary ?? "no answer"}`, seeded.result ?? {});
      frame = await open(page);
      const evidencePop = [await screenshot(page, "populated-1280")];
      for (const [index, text] of (plan.seed_shows ?? []).entries()) {
        const seen = await visible(frame, text);
        check(`ui.populated.shows.${index + 1}`, seen ? "passed" : "failed", seen ? `shows "${text}" with saved data` : `"${text}" is not visible with saved data`, {}, evidencePop);
      }
      cleanCheck("ui.populated.clean", mark, "populated state");
      await layout(page, 768, "populated");
    }

    // 4. A failed read must show an error, not an empty or blank screen.
    mark = errors.length;
    state.faults.records = true;
    frame = await open(page);
    const readAlert = await alertShown(frame);
    const stillTitled = (await frame.locator("h1").count()) > 0;
    check("ui.error.read", readAlert && stillTitled ? "passed" : "failed", readAlert ? (stillTitled ? `a failed read shows: ${readAlert}` : "a failed read blanked the screen") : "a failed read shows no error (it would look like there is no data)", {}, [await screenshot(page, "error-read")]);
    cleanCheck("ui.error.read_clean", mark, "failed read");
    state.faults.records = false;

    // 5. A failed save must show an error, keep the input and store nothing.
    if (plan) {
      frame = await open(page);
      const collection = plan.saved_collection;
      const before = collection ? (await ask({ kind: "control", op: "count", collection })).result?.count : null;
      state.faults.action = true;
      const invokesBefore = state.invokes;
      const done = await perform(page, frame, plan.primary);
      await settle(page);
      const evidenceSave = [await screenshot(page, "error-save")];
      if (!done.ok) {
        check("ui.error.save", "failed", done.message, {}, evidenceSave);
      } else if (state.invokes === invokesBefore) {
        check("ui.error.save", plan.saved ? "failed" : "skipped", "the interaction invoked no action, so a failed save could not be shown", {}, evidenceSave);
      } else {
        const saveAlert = await alertShown(frame);
        check("ui.error.save", saveAlert ? "passed" : "failed", saveAlert ? `a failed save shows: ${saveAlert}` : "a failed save shows no error; the person would think it was saved", {}, evidenceSave);
        if (collection) {
          const after = (await ask({ kind: "control", op: "count", collection })).result?.count;
          check("ui.error.save_nothing_stored", after === before ? "passed" : "failed", after === before ? "nothing was stored by the failed save" : `the failed save still stored data (${before} → ${after})`, { before, after });
        }
        const firstFill = plan.primary.find((s) => s.kind === "fill");
        if (firstFill) {
          const value = await (await control(frame, "fill", firstFill.label)).inputValue().catch(() => null);
          check("ui.error.save_input_kept", value === firstFill.text ? "passed" : "failed", value === firstFill.text ? "the typed input is kept after a failed save" : "the typed input was lost after a failed save", { value }, [], false);
        }
      }
      state.faults.action = false;
    }
    environment.blocked_requests = String((state.blocked ?? []).length);
  } finally {
    await browser.close().catch(() => undefined);
    out({ kind: "result", output: { environment, checks: checks.length } });
  }
}
