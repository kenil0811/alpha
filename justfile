# Alpha development commands. Exercised recipes only; see docs/alpha-r2 Implementation Blueprint §9.

set shell := ["bash", "-euo", "pipefail", "-c"]
export PYTHONDONTWRITEBYTECODE := "1"

# Pinned Node (see package.json engines). A Homebrew node@24 keg is preferred automatically when
# present; otherwise the node on PATH must match the pin (verify-locks checks it).
node_keg := "/opt/homebrew/opt/node@24/bin"
export PATH := if path_exists(node_keg) == "true" { node_keg + ":" + env_var("PATH") } else { env_var("PATH") }

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
    pnpm --filter @alpha/desktop typecheck
    uv run pytest packages/contracts services/core -q

# Python unit tests (contracts + core).
test-core:
    uv run pytest packages/contracts services/core -q

# Shell component/interaction tests and bridge protocol tests.
test-ui:
    pnpm --filter @alpha/ui-bridge test
    pnpm --filter @alpha/desktop test

# Real processes, SQLite and loopback transport.
test-integration:
    uv run pytest tests/integration -q -m integration

# Verify committed locks and exact tool versions (F01.C05).
verify-locks:
    uv run python tools/verify_locks.py

# Opt-in live builder qualification on the founder's Claude subscription (F02.C01). Writes evidence logs.
qualify-builder *args:
    uv run python tools/qualify_builder.py {{args}}

# F03 local containment feasibility probes on the pinned sandbox-runtime candidate (real macOS seatbelt).
qualify-sandbox *args:
    uv run python tests/qualification/sandbox/run_probes.py {{args}}

# Ticket verification dispatcher; unknown/unimplemented tickets fail.
verify-ticket ticket:
    uv run python tools/verify_ticket.py {{ticket}}

# Prepare the platform-managed Core runtime used by the desktop host (not the user's Python).
bundle-core:
    uv run python tools/bundle_core.py

# Run the desktop app in development (Vite shell + Tauri host + bundled Core).
dev: bundle-core
    pnpm --filter @alpha/desktop tauri dev
