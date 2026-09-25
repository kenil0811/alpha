# Alpha

Alpha is the platform through which nontechnical users create their own tools, automations,
one-off tasks and artifacts. This repository is the clean-start R2 implementation. The immutable
planning snapshot lives in [docs/alpha-r2](docs/alpha-r2) (start with its START_HERE.md); actual
progress is recorded in [docs/development](docs/development).

**Status: internal development build.** F01–F05 are complete (desktop/Core/worker bootstrap,
real builder route, UI isolation, conversation to SolutionBrief, records/artifacts/model SDK on a
shared App runtime profile). F06–F08 remain before the M1 review. See
[docs/development/task_state.json](docs/development/task_state.json).

## Toolchain (exact pins)

| Tool | Version | Pinned in |
|---|---|---|
| uv | 0.12.17 | `pyproject.toml` (`tool.uv.required-version`) |
| Python | 3.13.9 (uv-managed) | `.python-version` |
| pnpm | 10.34.5 | `package.json` (`packageManager`) |
| Node | 24.21.0 | `package.json` (`engines`), `.nvmrc` |
| Rust | 1.98.1 | `rust-toolchain.toml` |
| just | 1.58.0 | development convenience only |

`just verify-locks` checks that the tools on PATH match these pins and that the committed
`uv.lock` / `pnpm-lock.yaml` are exact. The justfile prefers a Homebrew `node@24` keg when present.

## Commands

```bash
just install            # uv sync --frozen && pnpm install --frozen-lockfile
just check              # format, lint, types, contract drift, fast tests
just test-core          # Python unit tests
just test-ui            # shell component/interaction tests (vitest + Testing Library)
just test-integration   # real Core process, SQLite, worker processes, loopback auth
just bundle-core        # prepare the Core runtime and publish the App runtime profile in .alpha-runtime/
just dev                # run the desktop app (Vite shell + Tauri host + bundled Core)
just verify-ticket F05  # ticket dispatcher; unknown/unimplemented tickets fail
just qualify-app-models DIR  # opt-in live ctx.models smoke on the Claude Code CLI route
```

## Layout

- `apps/desktop` — trusted React shell (`src`) and Tauri 2 native host (`src-tauri`).
- `services/core` — Python Core: loopback transport, control store, run coordinator, worker supervisor.
- `packages/contracts` — Python contract source (0.2), exported JSON Schema and generated TypeScript.
- `packages/app-sdk` — `alpha_sdk`, the only interface generated App/Task code uses
  (`ctx.records`, `ctx.artifacts`, `ctx.models`); standard library only.
- `workers/app` — the App worker that runs a sealed Version's handlers inside the runtime profile.
- `packages/ui-bridge` — the MessagePort bridge between generated UI and the shell.
- `tests/fixtures/apps` — two neutral fixture Apps used by the F05 integration tests.
- `tests/integration` — real-component tests.
- `tools` — verification and runtime bundling scripts.

## How the desktop path works (F01)

The Tauri host launches Core from the platform-managed runtime (`.alpha-runtime`, never the user's
Python) with an allowlisted environment and a random session token. Core binds `127.0.0.1` on an
OS-assigned port and prints one readiness line. The shell obtains the port and token through a
typed host command and authenticates every request with a bearer credential; origin and Host
headers are checked as well. Runs are persisted in SQLite (`control.sqlite` in the app data
directory) and streamed to the shell over SSE from a durable cursor. Closing the window hides it
and keeps the runtime and tray alive; explicit quit (tray menu, app menu or Cmd+Q) terminates the
Core process, which terminates every worker process tree and marks their runs interrupted.

## How generated App code runs (F05)

`just bundle-core` publishes the default App runtime profile (`pyprof-<id>`): the pinned CPython
plus reproducible `alpha-sdk` and `alpha-app-worker` wheels, installed from a hash-pinned lock,
sealed read-only. Core verifies every published profile at startup and never installs packages.
An App package (`app.yaml` + `src/`) is sealed into an immutable, content-addressed Version; its
handlers are resolved in a disposable worker on the exact profile. Each action run launches a
fresh worker with that profile's interpreter, private scratch and a per-run workload token. The
worker reaches records, artifacts and model calls only through JSON messages on its own pipes;
Core picks the App store from the run, never from the message. See
[docs/development/decisions/2026-09-25-f05-worker-channel-and-default-profile.md](docs/development/decisions/2026-09-25-f05-worker-channel-and-default-profile.md).
