// The real desktop shell (its production Vite build) in the pinned headless browser, against a
// real Core. Measures how much of the window each surface uses and follows a request through
// navigation and a reload. Evidence for M1-R01 (review findings F01, F02); the native window is
// checked separately.
//
// Usage: node tests/ui/shell_probe.mjs <job.json>   (prints one JSON result line)
//   job: {dist_dir, browser, evidence_dir, widths: [1100, 768], request}
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ORIGIN, openShell } from "./shell_page.mjs";

const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const { browser, page, errors } = await openShell(job);
const result = { layouts: [], continuity: {}, errors };
try {
  await page.goto(`${ORIGIN}/`);
  await page.getByText("Runtime connected").waitFor({ timeout: 20_000 });

  const measure = async (surface, width) => {
    const box = await page.evaluate(() => {
      const main = document.querySelector("main.main");
      const style = getComputedStyle(main);
      const available = main.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const section = main.querySelector(":scope > section.page");
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
    for (const surface of ["Home", "Activity"]) {
      await page.getByRole("navigation", { name: "Alpha" }).getByRole("button", { name: surface, exact: true }).click();
      await page.waitForTimeout(250);
      await measure(surface, width);
    }
  }

  // Continuity: a request stays reachable while Alpha is working on it, and after a reload.
  await page.setViewportSize({ width: 1280, height: 760 });
  const rail = page.getByRole("navigation", { name: "Alpha" });
  await page.getByLabel("What do you want done?").fill(job.request);
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText("Thinking about your request").waitFor({ timeout: 10_000 });
  await rail.getByRole("button", { name: "Activity", exact: true }).click();
  await rail.getByRole("button", { name: "Settings", exact: true }).click();
  await rail.getByRole("button", { name: "Home", exact: true }).click();
  const asked = page.locator(".msg--user", { hasText: job.request });
  result.continuity.request_shown_after_navigation = await asked.waitFor({ timeout: 10_000 }).then(() => true, () => false);
  // The answer is the proposal card (a new module is shaped first) or, once picked, Create it.
  await page.getByRole("button", { name: "Go with this", exact: true }).or(page.getByRole("button", { name: "Create it" })).first().waitFor({ timeout: 60_000 });
  result.continuity.answered_after_navigation = true;
  await page.reload();
  await page.getByText("Runtime connected").waitFor({ timeout: 20_000 });
  result.continuity.request_shown_after_reload = await asked.waitFor({ timeout: 10_000 }).then(() => true, () => false);
  await page.screenshot({ path: join(job.evidence_dir, "shell-assistant-after-reload.png") });
} catch (error) {
  result.error = String(error?.stack ?? error).slice(0, 2000);
  result.page_text = await page.evaluate(() => document.body.innerText.slice(0, 1500)).catch(() => null);
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify(result) + "\n");
