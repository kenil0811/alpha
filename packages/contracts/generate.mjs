// Generate TypeScript types from packages/contracts/schema/*.schema.json.
// `--check` fails on drift instead of writing. Python is the source of truth.
import { compile } from "json-schema-to-typescript";
import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const schemaDir = join(here, "schema");
const outDir = join(here, "ts");
const check = process.argv.includes("--check");
mkdirSync(outDir, { recursive: true });

const files = readdirSync(schemaDir).filter((f) => f.endsWith(".schema.json")).sort();
const drift = [];
const names = [];
const roots = [];
for (const file of files) {
  const schema = JSON.parse(readFileSync(join(schemaDir, file), "utf8"));
  const base = file.replace(".schema.json", "");
  const ts = await compile(schema, schema.title ?? base, {
    bannerComment: `/* Generated from ${file} (contract ${schema["x-alpha-contract-version"]}). Do not edit. */`,
    additionalProperties: false,
    style: { singleQuote: false, semi: true },
  });
  const target = join(outDir, `${base}.ts`);
  names.push(base);
  roots.push({ base, title: schema.title ?? base });
  if (check) {
    if (!existsSync(target) || readFileSync(target, "utf8") !== ts) drift.push(`${base}.ts`);
  } else {
    writeFileSync(target, ts);
  }
}
const index = roots.map(({ base, title }) => `export type { ${title} } from "./${base}";`).join("\n") + "\n";
const indexPath = join(outDir, "index.ts");
if (check) {
  if (!existsSync(indexPath) || readFileSync(indexPath, "utf8") !== index) drift.push("index.ts");
  if (drift.length) {
    console.error(`contract TypeScript drift: ${drift.join(", ")} (run: just contracts)`);
    process.exit(1);
  }
  console.log(`contract TypeScript up to date (${names.length} files)`);
} else {
  writeFileSync(indexPath, index);
  console.log(`wrote ${names.length} contract TypeScript files to ${outDir}`);
}
