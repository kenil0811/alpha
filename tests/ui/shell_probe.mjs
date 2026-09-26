// The real desktop shell (its production Vite build) in the pinned headless browser, against a
// real Core. Measures how much of the window each surface uses and follows a request through
// navigation and a reload. Evidence for M1-R01 (review findings F01, F02); the native window is
// checked separately.
//
// Usage: node tests/ui/shell_probe.mjs <job.json>   (prints one JSON result line)
//   job: {dist_dir, browser, evidence_dir, widths: [1100, 768], request}
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const { chromium } = await import(pathToFileURL(join(REPO, "workers/validator/node_modules/playwright-core/index.mjs")).href);
const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const ORIGIN = "http://localhost:1420";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };

// The shell is served from an intercepted http://localhost:1420, which Chrome does not treat as
// loopback, so its Local Network Access check would block the call to Core on 127.0.0.1. The
// native host has no such check; Core's own origin allow-list still applies here.
const browser = await chromium.launch({
  executablePath: job.browser,
  args: ["--disable-features=LocalNetworkAccessChecks,BlockInsecurePrivateNetworkRequests"],
});
const result = { layouts: [], continuity: {}, errors: [] };
try {
  const context = await browser.newContext({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 1 });
  await context.route(`${ORIGIN}/**`, async (route) => {
    const url = new URL(route.request().url());
    const rel = normalize(url.pathname === "/" ? "index.html" : url.pathname.slice(1));
    const file = join(job.dist_dir, rel);
    if (rel.startsWith("..") || !existsSync(file)) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ status: 200, contentType: TYPES[extname(file)] ?? "application/octet-stream", body: readFileSync(file) });
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => result.errors.push(String(e).slice(0, 300)));
  page.on("console", (m) => m.type() === "error" && result.errors.push(`console: ${m.text().slice(0, 300)}`));
  result.page = page;
  mkdirSync(job.evidence_dir, { recursive: true });
  await page.goto(`${ORIGIN}/`);
  await page.getByText("Runtime connected").waitFor({ timeout: 20_000 });

  const measure = async (surface, width) => {
    const box = await page.evaluate(() => {
      const main = document.querySelector("main.frame__main");
      const style = getComputedStyle(main);
      const available = main.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const section = main.querySelector(":scope > section");
      const rect = section.getBoundingClientRect();
      const doc = document.scrollingElement;
      return {
        window_width: window.innerWidth,
        available: Math.round(available),
        surface_width: Math.round(rect.width),
        surface_left: Math.round(rect.left - main.getBoundingClientRect().left - parseFloat(style.paddingLeft)),
        sideways_scroll: doc.scrollWidth > doc.clientWidth + 1,
      };
    });
    const shot = join(job.evidence_dir, `shell-${surface.replace(/\s+/g, "-").toLowerCase()}-${width}.png`);
    await page.screenshot({ path: shot });
    result.layouts.push({ surface, width, ...box, screenshot: shot });
  };

  for (const width of job.widths) {
    await page.setViewportSize({ width, height: 760 });
    for (const surface of ["Assistant", "My workflows", "Activity"]) {
      await page.getByRole("button", { name: surface, exact: true }).click();
      await page.waitForTimeout(250);
      await measure(surface, width);
    }
  }

  // Continuity: a request stays reachable while Alpha is working on it, and after a reload.
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await page.getByLabel("What do you want done?").fill(job.request);
  await page.getByRole("button", { name: "Ask Alpha" }).click();
  await page.getByText("Thinking about your request").waitFor({ timeout: 10_000 });
  await page.getByRole("button", { name: "My workflows", exact: true }).click();
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  const asked = page.locator(".bubble--user", { hasText: job.request });
  result.continuity.request_shown_after_navigation = await asked.waitFor({ timeout: 10_000 }).then(() => true, () => false);
  await page.getByRole("button", { name: "Create it" }).waitFor({ timeout: 20_000 });
  result.continuity.answered_after_navigation = true;
  await page.reload();
  await page.getByText("Runtime connected").waitFor({ timeout: 20_000 });
  result.continuity.request_shown_after_reload = await asked.waitFor({ timeout: 10_000 }).then(() => true, () => false);
  await page.screenshot({ path: join(job.evidence_dir, "shell-assistant-after-reload.png") });
} catch (error) {
  result.error = String(error?.stack ?? error).slice(0, 2000);
  result.page_text = await result.page?.evaluate(() => document.body.innerText.slice(0, 1500)).catch(() => null);
} finally {
  delete result.page;
  await browser.close();
}
process.stdout.write(JSON.stringify(result) + "\n");
