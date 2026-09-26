// Shared by the shell probes: the real desktop shell (its production Vite build), served from an
// intercepted http://localhost:1420 in the pinned headless browser, talking to a real Core.
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const { chromium } = await import(pathToFileURL(join(REPO, "workers/validator/node_modules/playwright-core/index.mjs")).href);
export const ORIGIN = "http://localhost:1420";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };

/** Opens the shell from `job.dist_dir`; page errors and console errors collect in `errors`. */
export async function openShell(job) {
  // Chrome does not treat the intercepted localhost:1420 as loopback, so its Local Network Access
  // check would block the call to Core on 127.0.0.1. The native host has no such check; Core's
  // own origin allow-list still applies here.
  const browser = await chromium.launch({
    executablePath: job.browser,
    args: ["--disable-features=LocalNetworkAccessChecks,BlockInsecurePrivateNetworkRequests"],
  });
  const context = await browser.newContext({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 1 });
  await context.route(`${ORIGIN}/**`, async (route) => {
    const url = new URL(route.request().url());
    const rel = normalize(url.pathname === "/" ? "index.html" : url.pathname.slice(1));
    const file = join(job.dist_dir, rel);
    if (rel.startsWith("..") || !existsSync(file)) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ status: 200, contentType: TYPES[extname(file)] ?? "application/octet-stream", body: readFileSync(file) });
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text().slice(0, 300)}`));
  mkdirSync(job.evidence_dir, { recursive: true });
  return { browser, context, page, errors };
}
