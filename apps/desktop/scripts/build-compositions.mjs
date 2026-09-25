// Build the two neutral kit compositions (tests/ui/compositions) with the platform's trusted UI
// build tool against the published UI build profile, for the shell's "UI kit fixture" panel.
// Without a published profile (run `just bundle-core`), placeholders explain what is missing.
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../../..");
// Build reports (stamps) live beside the fixture code; the HTML is served as a static file from
// the shell's own origin (public/), because a srcdoc frame would inherit the shell's CSP.
const outDir = resolve(here, "../src/qualification/compositions");
const publicDir = resolve(here, "../public/qualification/compositions");
const profilesRoot = join(repo, ".alpha-runtime", "profiles");
const names = ["review", "entry"];
mkdirSync(outDir, { recursive: true });
mkdirSync(publicDir, { recursive: true });

const profiles = existsSync(profilesRoot)
  ? readdirSync(profilesRoot)
      .filter((n) => n.startsWith("uiprof-"))
      .map((n) => join(profilesRoot, n))
      .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)
  : [];
const placeholder = (name, reason) =>
  `<!doctype html><html lang="en"><head><meta charset="UTF-8" /><meta http-equiv="Content-Security-Policy" content="default-src 'none'" /></head><body><p>Composition "${name}" is not built: ${reason}</p></body></html>\n`;

function digestDir(dir) {
  const hash = createHash("sha256");
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) hash.update(digestDir(path));
    else hash.update(name).update(readFileSync(path));
  }
  return hash.digest("hex");
}

for (const name of names) {
  const target = join(publicDir, `${name}.html`);
  const buildInfo = join(outDir, `${name}.build.json`);
  if (profiles.length === 0) {
    writeFileSync(target, placeholder(name, "no UI build profile is published; run `just bundle-core`."));
    writeFileSync(buildInfo, "{}\n");
    continue;
  }
  const source = join(repo, "tests", "ui", "compositions", name);
  const stamp = `${profiles[0]}:${digestDir(source)}`;
  if (existsSync(target) && existsSync(buildInfo) && readFileSync(buildInfo, "utf8").includes(JSON.stringify(stamp))) {
    console.log(`composition ${name} up to date`);
    continue;
  }
  const work = mkdtempSync(join(tmpdir(), "alpha-composition-"));
  try {
    execFileSync("node", [join(repo, "tools", "ui_build", "build_app_ui.mjs"), "--profile", profiles[0], "--src", source, "--out", work], { stdio: "inherit" });
    writeFileSync(target, readFileSync(join(work, "index.html")));
    const report = JSON.parse(readFileSync(join(work, "build.json"), "utf8"));
    writeFileSync(buildInfo, JSON.stringify({ ...report, stamp }, null, 2) + "\n");
    console.log(`composition ${name} built with ${report.profile.profile_id}`);
  } catch (error) {
    writeFileSync(target, placeholder(name, `the build failed (${error instanceof Error ? error.message : error}).`));
    writeFileSync(buildInfo, "{}\n");
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
}
