/**
 * Alpha's browser session worker (the `browser` capability). One JSON job on stdin, one JSON
 * result on stdout, then exit. Two jobs:
 *   signin: open a visible window on a profile Alpha keeps, so the person signs in themselves;
 *           resolves when they close the window. Alpha never reads what they type.
 *   read:   load a page headless (with a profile, or none), let scripts run, and return its
 *           title, readable text and links. Never clicks, types or submits anything.
 *   status: whether a profile holds cookies for a site.
 */
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { createInterface } from "node:readline";

function out(value) {
  process.stdout.write(JSON.stringify(value) + "\n");
}

// Headless Chromium announces itself ("HeadlessChrome"), and sites answer with a wall. The
// session reads as the person's own Chrome would: a normal user agent, no automation flag, and
// the installed Chrome when Alpha asks for it (job.channel = "chrome").
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36";

function launchOptions(job, headless) {
  return {
    headless,
    channel: job.channel || undefined,
    executablePath: job.browser || undefined,
    viewport: { width: 1280, height: 900 },
    locale: job.locale || "en-GB",
    userAgent: USER_AGENT,
    ignoreDefaultArgs: ["--enable-automation"],
    args: ["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check", "--disable-blink-features=AutomationControlled"],
  };
}

function cookieMatches(cookie, site) {
  const domain = String(cookie.domain || "").replace(/^\./, "").toLowerCase();
  return domain === site || domain.endsWith("." + site);
}

async function cookiesFor(job) {
  const context = await chromium.launchPersistentContext(job.profile, launchOptions(job, true));
  try {
    const cookies = await context.cookies();
    return cookies.filter((c) => cookieMatches(c, job.site)).length;
  } finally {
    await context.close();
  }
}

async function signin(job) {
  mkdirSync(job.profile, { recursive: true, mode: 0o700 });
  const context = await chromium.launchPersistentContext(job.profile, launchOptions(job, false));
  const page = context.pages()[0] || (await context.newPage());
  await page.goto(job.url, { waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {});
  await new Promise((resolve) => {
    context.on("close", resolve);
    const maybeDone = async () => {
      if (context.pages().length === 0) {
        try {
          await context.close();
        } catch {
          // already closing
        }
        resolve();
      }
    };
    context.on("page", (p) => p.on("close", maybeDone));
    page.on("close", maybeDone);
  });
  const cookies = await cookiesFor(job);
  return { signed_in: cookies > 0, cookies };
}

async function status(job) {
  const cookies = await cookiesFor(job);
  return { signed_in: cookies > 0, cookies };
}

async function read(job) {
  const maxChars = job.max_chars || 60000;
  let browser = null;
  let context;
  if (job.profile) {
    context = await chromium.launchPersistentContext(job.profile, launchOptions(job, true));
  } else {
    browser = await chromium.launch(launchOptions(job, true));
    context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: job.locale || "en-GB", userAgent: USER_AGENT });
  }
  try {
    const page = context.pages()[0] || (await context.newPage());
    const response = await page.goto(job.url, { waitUntil: "domcontentloaded", timeout: job.timeout_ms || 30000 });
    await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {});
    for (let i = 0; i < (job.scroll || 0); i += 1) {
      await page.mouse.wheel(0, 2400);
      await page.waitForTimeout(500);
    }
    const data = await page.evaluate((limit) => {
      const links = [];
      const seen = new Set();
      const tidy = (value, max) => String(value || "").replace(/\s+/g, " ").trim().slice(0, max);
      for (const a of document.querySelectorAll("a[href]")) {
        const href = a.href;
        if (!/^https?:/i.test(href)) continue;
        const url = href.split("#")[0];
        if (seen.has(url) || links.length >= 400) continue;
        seen.add(url);
        // A link that wraps an image or an icon has no text of its own: fall back to what it
        // labels, and always carry the text of the card it sits in (name, title, company).
        const own = tidy(a.innerText || a.textContent, 200);
        const img = a.querySelector("img");
        const text = own || tidy(a.getAttribute("aria-label") || a.getAttribute("title") || (img && img.getAttribute("alt")), 200);
        // The card: the smallest ancestor with a short text of its own (a row, an item), not
        // the list it belongs to.
        let near = "";
        let node = a.parentElement;
        for (let depth = 0; node && node !== document.body && depth < 6; depth += 1) {
          const words = tidy(node.innerText, 400);
          if (words.length > own.length + 3 && words.length <= 300) {
            near = words.slice(0, 240);
            if (words.length >= 25) break;
          }
          if (words.length > 300) break;
          node = node.parentElement;
        }
        links.push({ text, url, near });
      }
      const text = document.body ? document.body.innerText : "";
      return { title: document.title, text: text.slice(0, limit), truncated: text.length > limit, links };
    }, maxChars);
    const finalUrl = page.url();
    const wall = /\/(login|authwall|checkpoint|signin|sign-in|signup|uas\/login)/i;
    const blocked = wall.test(finalUrl) && !wall.test(job.url);
    return {
      status: response ? response.status() : 0,
      final_url: finalUrl,
      content_type: "text/html",
      title: data.title || null,
      text: data.text,
      truncated: data.truncated,
      links: data.links,
      blocked,
    };
  } finally {
    await context.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
  }
}

const rl = createInterface({ input: process.stdin });
rl.once("line", async (line) => {
  let job;
  try {
    job = JSON.parse(line);
  } catch {
    out({ error: "the job was not JSON" });
    process.exit(2);
  }
  try {
    if (job.op === "signin") out(await signin(job));
    else if (job.op === "read") out(await read(job));
    else if (job.op === "status") out(await status(job));
    else out({ error: `unknown job ${job.op}` });
  } catch (error) {
    out({ error: String((error && error.message) || error) });
  }
  process.exit(0);
});
