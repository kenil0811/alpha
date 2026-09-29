// A whole journey through the real desktop shell (its production Vite build) in the pinned
// headless browser, against a real Core: ask, create, open the result, save an entry with its
// main action, meet a refusal, and find the App, its data and its runs again after a reload.
// Evidence for M1-R06 (review finding F05: acceptance must exercise the shell a person uses).
// The routes are the deterministic control fixtures, so this proves the shell and platform path,
// never generation quality; generated screens and live generation are observed in the Alpha
// window.
//
// Usage: node tests/ui/shell_journey.mjs <job.json>   (prints one JSON result line)
//   job: {dist_dir, browser, evidence_dir, request, builder_hint, entry, too_long}
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ORIGIN, openShell } from "./shell_page.mjs";

const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const { browser, context, page, errors } = await openShell(job);
const result = { steps: {}, errors };
const shot = (name) => page.screenshot({ path: join(job.evidence_dir, `journey-${name}.png`), fullPage: true });
try {
  // The control builder's package is chosen per creation. The shell sends no hint, so the probe
  // adds the fixture's to that one request; nothing else the shell sends is changed.
  await context.route("**/api/conversations/*/creations", (route) => {
    const request = route.request();
    if (request.method() !== "POST") return route.continue();
    const body = JSON.parse(request.postData() || "{}");
    return route.continue({ postData: JSON.stringify({ ...body, builder_hint: job.builder_hint }) });
  });
  await page.goto(`${ORIGIN}/`);
  await page.getByText("Runtime connected").waitFor({ timeout: 20_000 });

  // Ask and create.
  await page.getByLabel("What do you want done?").fill(job.request);
  await page.getByRole("button", { name: "Send" }).click();
  // A new module is researched and shaped first: the proposal card offers "Go with this" on
  // Alpha's pick, and the choice becomes the brief that "Create it" then builds.
  const pick = page.getByRole("button", { name: "Go with this", exact: true });
  const create = page.getByRole("button", { name: "Create it" });
  await pick.or(create).first().waitFor({ timeout: 60_000 });
  if (await pick.isVisible()) await pick.click();
  await create.click({ timeout: 60_000 });
  const ready = page.getByLabel(/ is ready$/);
  await ready.waitFor({ timeout: 240_000 });
  result.steps.ready = await ready.innerText();
  await shot("ready");

  // Open it: the module opens on its Notes table; the actions a person runs by hand sit on
  // the Actions tab, the main one first.
  await ready.getByRole("button", { name: /^Open / }).click();
  const tab = (name) => page.getByRole("tab", { name, exact: true });
  await tab("Actions").click({ timeout: 10_000 });
  const main = page.locator("form.action--primary");
  await main.waitFor({ timeout: 10_000 });
  result.steps.main_action = await main.locator("h3").innerText();
  const title = main.getByLabel("Title");
  await title.fill(job.entry);
  await main.getByRole("button", { name: "Run" }).click();
  await main.getByRole("status").waitFor({ timeout: 60_000 });
  result.steps.saved = await main.getByRole("status").innerText();

  // A refusal: said in plain words, what was typed is kept, and nothing is saved.
  await title.fill(job.too_long);
  await main.getByRole("button", { name: "Run" }).click();
  await main.getByRole("alert").waitFor({ timeout: 60_000 });
  result.steps.refusal = await main.getByRole("alert").innerText();
  result.steps.refusal_kept_input = (await title.inputValue()) === job.too_long;
  await shot("refusal");
  // What was saved is on the Notes page Alpha draws for the table.
  await tab("Notes").click();
  const saved = page.getByRole("table");
  await saved.locator("tbody tr").first().waitFor({ timeout: 10_000 });
  result.steps.saved_data = await saved.innerText();

  // A computing action under More actions reports on the saved data in plain words.
  await tab("Actions").click();
  await page.getByText(/^More actions/).click();
  const count = page.locator("form.action", { has: page.locator("h3", { hasText: "Count notes" }) });
  await count.getByRole("button", { name: "Run" }).click();
  await count.getByRole("status").waitFor({ timeout: 60_000 });
  result.steps.count = await count.getByRole("status").innerText();

  // Reload: the App, its data and its runs are all still there.
  await page.reload();
  await page.getByText("Runtime connected").waitFor({ timeout: 20_000 });
  await page.getByRole("navigation", { name: "Alpha" }).getByRole("button", { name: "Home", exact: true }).click();
  const open = page.getByRole("button", { name: /^Open / }).first();
  await open.waitFor({ timeout: 10_000 });
  result.steps.listed_after_reload = await open.getAttribute("aria-label");
  await open.click();
  const savedAgain = page.getByRole("table");
  await savedAgain.locator("tbody tr").first().waitFor({ timeout: 10_000 });
  result.steps.saved_after_reload = await savedAgain.innerText();
  await page.getByRole("navigation", { name: "Alpha" }).getByRole("button", { name: "Activity", exact: true }).click();
  const runs = page.getByRole("list", { name: "Runs" });
  await runs.waitFor({ timeout: 10_000 });
  result.steps.activity = await runs.locator(".run__head").allInnerTexts();
  result.steps.activity_not_done = await runs.locator(".run .notice").allInnerTexts();
  // The run list lines up with the Activity heading (no stray list indent).
  const heading = await page.getByRole("heading", { name: "Activity" }).boundingBox();
  const card = await runs.locator(".run").first().boundingBox();
  result.steps.activity_indent = Math.round(card.x - heading.x);
  await shot("activity");
} catch (error) {
  result.error = String(error?.stack ?? error).slice(0, 2000);
  result.page_text = await page.evaluate(() => document.body.innerText.slice(0, 2000)).catch(() => null);
  await shot("error").catch(() => undefined);
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify(result) + "\n");
