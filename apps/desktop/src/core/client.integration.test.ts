/** Real Core process + real HttpCoreClient over Node's fetch. Run with `just test-ui`. */
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { HttpCoreClient, type StreamItem } from "./client";

const REPO_ROOT = resolve(__dirname, "../../../..");
const PYTHON = join(REPO_ROOT, ".venv/bin/python");
const TOKEN = "n".repeat(64);

let core: ChildProcess;
let client: HttpCoreClient;

beforeAll(async () => {
  const dataDir = mkdtempSync(join(tmpdir(), "alpha-client-it-"));
  core = spawn(PYTHON, ["-m", "alpha.main"], {
    cwd: REPO_ROOT,
    env: {
      ALPHA_DATA_DIR: dataDir,
      ALPHA_SESSION_TOKEN: TOKEN,
      ALPHA_ALLOWED_ORIGINS: "http://localhost:1420",
      ALPHA_WATCH_PARENT: "0",
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", "pipe", "inherit"],
  });
  const port = await new Promise<number>((resolvePort, reject) => {
    let buffer = "";
    core.stdout!.on("data", (chunk: Buffer) => {
      buffer += chunk.toString();
      const line = buffer.split("\n").find((l) => l.startsWith("ALPHA_CORE_READY "));
      if (line) resolvePort(JSON.parse(line.slice("ALPHA_CORE_READY ".length)).port as number);
    });
    core.on("exit", (code) => reject(new Error(`core exited ${code}`)));
    setTimeout(() => reject(new Error("core not ready")), 20000);
  });
  client = new HttpCoreClient({ baseUrl: `http://127.0.0.1:${port}`, token: TOKEN });
}, 30000);

afterAll(() => {
  core?.kill("SIGTERM");
});

describe("HttpCoreClient against real Core", () => {
  it("streams every event of a run in order", async () => {
    const items: StreamItem[] = [];
    const controller = new AbortController();
    const finished = new Promise<void>((resolveDone) => {
      client.stream(
        0,
        (item) => {
          items.push(item);
          if (item.event.kind === "run.succeeded") {
            resolveDone();
            controller.abort();
          }
        },
        controller.signal,
      ).catch(() => undefined);
    });
    const run = await client.createRun({ text: "node stream", steps: 3, spawn_child: true });
    await finished;
    const stored = await client.events(run.run_id);
    expect(items.map((i) => i.event.sequence)).toEqual(stored.map((e) => e.sequence));
    expect(items.at(-1)?.run.state).toBe("succeeded");
    expect(stored).toHaveLength(10);
  }, 20000);
});
