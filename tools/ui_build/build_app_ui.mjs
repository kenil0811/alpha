// Trusted build of one App's UI source against the managed UI build profile (F06).
//
//   node tools/ui_build/build_app_ui.mjs --profile <uiprof dir> --src <ui source dir> --out <dir>
//
// The App supplies only source files (main.tsx plus its own .ts/.tsx/.css); the platform supplies
// the Vite configuration, plugins and every package from the sealed profile. Output is ONE static
// HTML document with a strict CSP (script and style pinned by SHA-256, no network, no forms,
// no navigation) plus build.json recording the exact profile, package identities, the resolved
// origin of every bundled module and output digests. The build fails if any module resolves
// outside the App's source or the profile (e.g. a workspace copy of the kit), or if the source
// tries a remote import.
import { createHash } from "node:crypto";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, value, index, all) => (value.startsWith("--") ? [...pairs, [value.slice(2), all[index + 1]]] : pairs), []),
);
for (const key of ["profile", "src", "out"]) {
  if (!args[key]) {
    console.error("usage: build_app_ui.mjs --profile <dir> --src <dir> --out <dir>");
    process.exit(2);
  }
}
const fail = (message) => {
  console.error(`ui build failed: ${message}`);
  process.exit(1);
};
const sha256 = (data) => createHash("sha256").update(data).digest("hex");

const profileDir = realpathSync(resolve(args.profile));
const srcDir = realpathSync(resolve(args.src));
const outDir = resolve(args.out);
const manifest = JSON.parse(readFileSync(join(profileDir, "manifest.json"), "utf8"));
if (manifest.kind !== "ui_build") fail(`${manifest.profile_id} is not a UI build profile`);
const toolchain = manifest.target.ui_toolchain ?? {};
if (process.version !== `v${toolchain.node}`) fail(`Node ${process.version} differs from the profile's ${toolchain.node}`);

// 1. Copy the App's source into a private work directory; only plain source files are allowed.
const ALLOWED = new Set([".tsx", ".ts", ".css", ".json"]);
const work = mkdtempSync(join(tmpdir(), "alpha-ui-build-"));
const sourceDigest = createHash("sha256");
const appFiles = [];
function copySource(dir) {
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name);
    const info = lstatSync(path);
    const rel = relative(srcDir, path);
    if (info.isSymbolicLink()) fail(`${rel} is a symbolic link`);
    if (info.isDirectory()) {
      if (name === "node_modules" || name.startsWith(".")) fail(`${rel} is not allowed in UI source`);
      mkdirSync(join(work, rel), { recursive: true });
      copySource(path);
      continue;
    }
    if (!ALLOWED.has(extname(name))) fail(`${rel} has a file type UI source cannot contain`);
    if (info.size > 500_000) fail(`${rel} is too large`);
    const bytes = readFileSync(path);
    sourceDigest.update(`${rel}\n`).update(bytes);
    appFiles.push(rel.split(sep).join("/"));
    cpSync(path, join(work, rel));
  }
}
copySource(srcDir);
if (!existsSync(join(work, "main.tsx"))) fail("the UI source needs a main.tsx entry");
writeFileSync(join(work, "index.html"), '<!doctype html><html lang="en"><head><meta charset="UTF-8" /></head><body><div id="root"></div><script type="module" src="./main.tsx"></script></body></html>');
symlinkSync(join(profileDir, "node_modules"), join(work, "node_modules"), "dir");

// 2. Load Vite and the React plugin from the profile only.
const requireFromProfile = createRequire(join(profileDir, "node_modules", "noop.js"));
const vite = await import(pathToFileURL(requireFromProfile.resolve("vite")).href);
const react = (await import(pathToFileURL(requireFromProfile.resolve("@vitejs/plugin-react")).href)).default;

const profileModules = realpathSync(join(profileDir, "node_modules"));
const workReal = realpathSync(work);
const packageCache = new Map();
function packageOf(file) {
  let dir = dirname(file);
  while (dir.startsWith(profileModules)) {
    if (packageCache.has(dir)) return packageCache.get(dir);
    const pkg = join(dir, "package.json");
    if (existsSync(pkg)) {
      const meta = JSON.parse(readFileSync(pkg, "utf8"));
      if (meta.name && meta.version) {
        const id = `${meta.name}@${meta.version}`;
        packageCache.set(dir, id);
        return id;
      }
    }
    dir = dirname(dir);
  }
  return null;
}

const provenance = { app: [], packages: {}, virtual: 0, violations: [] };
const REMOTE = /^(?:[a-z]+:)?\/\//i;
const guard = {
  name: "alpha-ui-guard",
  enforce: "pre",
  resolveId(source) {
    if (REMOTE.test(source) || source.startsWith("data:") || source.startsWith("http")) {
      this.error(`remote or inline-URL import "${source}" is not allowed in App UI`);
    }
    return null;
  },
  generateBundle(_options, bundle) {
    for (const item of Object.values(bundle)) {
      if (item.type !== "chunk") continue;
      const ids = item.moduleIds ?? Object.keys(item.modules ?? {});
      for (const raw of ids) {
        const id = raw.split("?")[0];
        if (id.startsWith("\0") || !id.startsWith("/")) {
          provenance.virtual += 1;
          continue;
        }
        let real;
        try {
          real = realpathSync(id);
        } catch {
          provenance.violations.push(id);
          continue;
        }
        if (real.startsWith(workReal + sep) && !real.includes(`${sep}node_modules${sep}`)) {
          provenance.app.push(relative(workReal, real).split(sep).join("/"));
        } else if (real.startsWith(profileModules + sep)) {
          const pkg = packageOf(real);
          if (!pkg) provenance.violations.push(real);
          else provenance.packages[pkg] = (provenance.packages[pkg] ?? 0) + 1;
        } else {
          provenance.violations.push(real);
        }
      }
    }
  },
};

const bundleDir = join(work, ".out");
try {
  await vite.build({
    root: work,
    configFile: false,
    envDir: false,
    publicDir: false,
    logLevel: "warn",
    mode: "production",
    plugins: [guard, react()],
    resolve: { preserveSymlinks: false },
    build: {
      outDir: bundleDir,
      emptyOutDir: true,
      modulePreload: false,
      cssCodeSplit: false,
      assetsInlineLimit: 100_000_000,
      sourcemap: false,
      minify: true,
      target: "safari15",
      rollupOptions: { output: { codeSplitting: false } },
    },
  });
} catch (error) {
  rmSync(work, { recursive: true, force: true });
  fail(error instanceof Error ? error.message : String(error));
}
if (provenance.violations.length) {
  rmSync(work, { recursive: true, force: true });
  fail(`modules resolved outside the App source and the profile: ${provenance.violations.slice(0, 5).join(", ")}`);
}

// 3. Inline into one document with a hash-pinned CSP.
const assets = join(bundleDir, "assets");
const read = (ext) =>
  existsSync(assets)
    ? readdirSync(assets).filter((f) => f.endsWith(ext)).sort().map((f) => readFileSync(join(assets, f), "utf8")).join("\n")
    : "";
const js = read(".js");
const css = read(".css");
const leftovers = existsSync(assets) ? readdirSync(assets).filter((f) => !f.endsWith(".js") && !f.endsWith(".css")) : [];
if (leftovers.length) fail(`unexpected emitted assets: ${leftovers.join(", ")}`);
if (/\bimport\s*\(\s*["'`](?:https?:)?\/\//.test(js) || /\bfrom\s*["'`](?:https?:)?\/\//.test(js)) fail("the bundle contains a remote import");
const scriptHash = createHash("sha256").update(js).digest("base64");
const styleHash = createHash("sha256").update(css).digest("base64");
const csp = [
  "default-src 'none'",
  `script-src 'sha256-${scriptHash}'`,
  css ? `style-src 'sha256-${styleHash}'` : "style-src 'none'",
  "connect-src 'none'",
  "img-src data:",
  "font-src 'none'",
  "form-action 'none'",
  "base-uri 'none'",
].join("; ");
const html = `<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<meta http-equiv="Content-Security-Policy" content="${csp}" />
<title>App</title>${css ? `<style>${css}</style>` : ""}</head>
<body><div id="root"></div><script type="module">${js}</script></body></html>
`;
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "index.html"), html);
writeFileSync(join(outDir, "index.csp"), csp);

const pins = Object.fromEntries(manifest.packages.map((p) => [`${p.name}@${p.version}`, p]));
const identity = (name) => {
  const pin = manifest.packages.find((p) => p.name === name);
  return pin ? { name, version: pin.version, artifact: pin.artifact, installed_tree_sha256: pin.artifact_sha256 } : null;
};
const report = {
  profile: { profile_id: manifest.profile_id, manifest_sha256: manifest.manifest_sha256 },
  node: process.version,
  kit: identity("@alpha/ui-kit"),
  bridge: identity("@alpha/ui-bridge"),
  react: identity("react"),
  source: { files: appFiles, sha256: sourceDigest.digest("hex") },
  modules: {
    app: [...new Set(provenance.app)].sort(),
    packages: Object.fromEntries(Object.entries(provenance.packages).sort()),
    unpinned: Object.keys(provenance.packages).filter((id) => !pins[id]),
    virtual: provenance.virtual,
  },
  output: {
    html_sha256: sha256(html),
    script_sha256: sha256(js),
    style_sha256: sha256(css),
    html_bytes: Buffer.byteLength(html),
  },
  csp,
};
if (report.modules.unpinned.length) fail(`bundled packages not in the profile inventory: ${report.modules.unpinned.join(", ")}`);
writeFileSync(join(outDir, "build.json"), JSON.stringify(report, null, 2) + "\n");
rmSync(work, { recursive: true, force: true });
console.log(JSON.stringify({ out: outDir, profile_id: manifest.profile_id, html_sha256: report.output.html_sha256, bytes: report.output.html_bytes }));
