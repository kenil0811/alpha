# Alpha development commands. Exercised recipes only; see docs/alpha-r2 Implementation Blueprint §9.

set shell := ["bash", "-euo", "pipefail", "-c"]
export PYTHONDONTWRITEBYTECODE := "1"

# Toolchain locations that are often missing from an interactive shell's PATH: the pinned
# Homebrew node@24 keg and rustup's cargo bin. Each is prepended only when present; the versions
# on PATH must still match the pins (verify-locks checks them).
node_keg := "/opt/homebrew/opt/node@24/bin"
cargo_bin := env_var("HOME") + "/.cargo/bin"
path_with_node := if path_exists(node_keg) == "true" { node_keg + ":" + env_var("PATH") } else { env_var("PATH") }
export PATH := if path_exists(cargo_bin) == "true" { cargo_bin + ":" + path_with_node } else { path_with_node }

default:
    @just --list

# Install platform dependencies exactly as locked (uv workspace + pnpm workspace).
install:
    uv sync --frozen
    pnpm install --frozen-lockfile

# Regenerate contract JSON Schema and TypeScript types from the Python contract source.
contracts:
    uv run python -m alpha_contracts.export
    pnpm --filter @alpha/contracts generate

# Formatting, lint, types, contract drift and fast deterministic tests.
check:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    uv run python -m alpha_contracts.export --check
    pnpm --filter @alpha/contracts check
    pnpm --filter @alpha/ui-bridge typecheck
    pnpm --filter @alpha/ui-kit typecheck
    pnpm --filter @alpha/ui-compositions typecheck
    pnpm --filter @alpha/desktop typecheck
    uv run pytest packages/contracts packages/app-sdk services/core -q

# Python unit tests (contracts + core).
test-core:
    uv run pytest packages/contracts packages/app-sdk services/core -q

# Shell component/interaction tests and bridge protocol tests.
test-ui:
    pnpm --filter @alpha/ui-bridge test
    pnpm --filter @alpha/ui-kit test
    pnpm --filter @alpha/desktop test

# Real processes, SQLite and loopback transport.
test-integration:
    uv run pytest tests/integration tests/ui -q -m integration

# Kit reference sheet (development only): every pattern and state with neutral data.
kit-reference:
    pnpm --filter @alpha/ui-kit reference

# Verify committed locks and exact tool versions (F01.C05).
verify-locks:
    uv run python tools/verify_locks.py

# Opt-in live builder qualification on the founder's Claude subscription (F02.C01). Writes evidence logs.
qualify-builder *args:
    uv run python tools/qualify_builder.py {{args}}

# Opt-in live assistant qualification on the founder's Claude subscription (F04.C01). Writes evidence logs.
qualify-assistant *args:
    uv run python tools/qualify_assistant.py {{args}}

# F05 supplementary live smoke: one ctx.models call on the Claude Code CLI route. Writes evidence.
qualify-app-models out_dir:
    uv run python tools/qualify_app_models.py {{out_dir}}

# F03 local containment feasibility probes on the pinned sandbox-runtime candidate (real macOS seatbelt).
qualify-sandbox *args:
    uv run python tests/qualification/sandbox/run_probes.py {{args}}

# Ticket verification dispatcher; unknown/unimplemented tickets fail.
verify-ticket ticket:
    uv run python tools/verify_ticket.py {{ticket}}

# Prepare the platform-managed Core runtime and publish the default App runtime profile
# (both used by the desktop host; neither is the user's Python).
bundle-core:
    uv run python tools/bundle_core.py
    uv run python tools/build_app_profile.py
    uv run python tools/build_ui_profile.py

# Run the desktop app in development (Vite shell + Tauri host + bundled Core).
dev: bundle-core
    pnpm --filter @alpha/desktop tauri dev

# Opt-in live F07 qualification on the Claude Code CLI route: repair | limit | generate.
qualify-build scenario:
    uv run python evals/qualify_build.py --scenario {{scenario}}
