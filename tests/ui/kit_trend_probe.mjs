// The kit's trend chart in the pinned headless browser at the widths an App's screen actually
// gets inside Alpha (M1 review finding F09). Prints one JSON line.
//   node tests/ui/kit_trend_probe.mjs <job.json>   job: {dist_dir, browser, evidence_dir, widths}
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const { chromium } = await import(pathToFileURL(join(REPO, "workers/validator/node_modules/playwright-core/index.mjs")).href);
const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const ORIGIN = "http://kit.alpha.invalid";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };
const browser = await chromium.launch({ executablePath: job.browser });
const result = { widths: {}, errors: [] };
try {
  const page = await browser.newPage({ viewport: { width: job.widths[0], height: 900 }, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => result.errors.push(String(e).slice(0, 300)));
  await page.route(`${ORIGIN}/**`, (route) => {
    const url = new URL(route.request().url());
    const rel = normalize(url.pathname === "/" ? "index.html" : url.pathname.slice(1));
    const file = join(job.dist_dir, rel);
    if (rel.startsWith("..") || !existsSync(file)) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ status: 200, contentType: TYPES[extname(file)] ?? "application/octet-stream", body: readFileSync(file) });
  });
  mkdirSync(job.evidence_dir, { recursive: true });
  for (const width of job.widths) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${ORIGIN}/index.html?charts=1`);
    await page.locator("[data-chart]").first().waitFor({ timeout: 15_000 });
    result.widths[width] = await page.evaluate(() => {
      const doc = document.scrollingElement;
      const charts = {};
      for (const el of document.querySelectorAll("[data-chart]")) {
        const plot = el.querySelector(".a-trend__plot, .a-trend__svg");
        const bars = el.querySelector(".a-trend__bars");
        const axisSizes = [...el.querySelectorAll(".a-trend__axis")].map((a) => {
          const r = a.getBoundingClientRect();
          const size = parseFloat(getComputedStyle(a).fontSize);
          return a instanceof SVGElement ? size * (plot.getBoundingClientRect().width / plot.viewBox.baseVal.width) : size;
        });
        charts[el.getAttribute("data-chart")] = {
          plot_height: Math.round(plot.getBoundingClientRect().height),
          plot_width: Math.round(plot.getBoundingClientRect().width),
          axis_px: Math.round(Math.max(0, ...axisSizes)),
          bars_overflow: bars ? bars.scrollWidth > bars.clientWidth + 1 : null,
          slots: el.querySelectorAll(".a-trend__slot").length,
          coverage: el.querySelector(".a-trend__legend")?.textContent ?? "",
        };
      }
      return { sideways_scroll: doc.scrollWidth > doc.clientWidth + 1, charts };
    });
    const shot = join(job.evidence_dir, `trend-${width}.png`);
    await page.screenshot({ path: shot, fullPage: true });
    result.widths[width].screenshot = shot;
  }
} catch (error) {
  result.error = String(error?.stack ?? error).slice(0, 2000);
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify(result) + "\n");
