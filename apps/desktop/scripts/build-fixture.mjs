// Build the generated-UI fixture into ONE self-contained HTML document with a strict CSP whose
// script-src is the hash of the inlined bundle. The shell mounts it via iframe srcdoc.
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { createHash } from "node:crypto";
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../fixtures/generated-ui");
const outDir = mkdtempSync(join(tmpdir(), "alpha-fixture-"));
const target = resolve(here, "../src/qualification/generated-ui.html");
const sources = [join(root, "main.tsx"), join(root, "index.html"), fileURLToPath(import.meta.url)];
const stamp = createHash("sha256");
for (const s of sources) stamp.update(readFileSync(s));
const stampHex = stamp.digest("hex");
if (existsSync(target) && readFileSync(target, "utf8").includes(`fixture-source-sha256=${stampHex}`)) {
  console.log("fixture up to date");
  process.exit(0);
}
await build({
  root,
  logLevel: "warn",
  plugins: [react()],
  build: { outDir, emptyOutDir: true, modulePreload: false, cssCodeSplit: false, sourcemap: false, minify: false, rollupOptions: { output: { inlineDynamicImports: true } } },
});
const assets = join(outDir, "assets");
const js = readdirSync(assets).filter((f) => f.endsWith(".js")).map((f) => readFileSync(join(assets, f), "utf8")).join("\n");
const css = readdirSync(assets).filter((f) => f.endsWith(".css")).map((f) => readFileSync(join(assets, f), "utf8")).join("\n");
const scriptHash = createHash("sha256").update(js).digest("base64");
const styleHash = createHash("sha256").update(css).digest("base64");
const csp = [
  "default-src 'none'",
  `script-src 'sha256-${scriptHash}'`,
  css ? `style-src 'sha256-${styleHash}'` : "style-src 'none'",
  "connect-src 'none'",
  "img-src data:",
  "form-action 'none'",
  "frame-ancestors *",
  "base-uri 'none'",
].join("; ");
const html = `<!doctype html>
<html lang="en"><head><meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy" content="${csp}" />
<!-- fixture-source-sha256=${stampHex} -->
<title>Generated UI fixture</title>${css ? `<style>${css}</style>` : ""}</head>
<body><div id="root"></div><script type="module">${js}</script></body></html>
`;
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, html);
rmSync(outDir, { recursive: true, force: true });
console.log(`fixture built: ${target} (${html.length} bytes, script sha256 ${scriptHash.slice(0, 12)}…)`);
