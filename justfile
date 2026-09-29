# Alpha development commands. Exercised recipes only.

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

# Verify committed locks and exact tool versions.
verify-locks:
    uv run python tools/verify_locks.py

# Prepare the platform-managed Core runtime and publish the default App runtime profile
# (both used by the desktop host; neither is the user's Python).
bundle-core:
    uv run python tools/bundle_core.py
    uv run python tools/build_app_profile.py
    uv run python tools/build_ui_profile.py

# Run the desktop app in development (Vite shell + Tauri host + bundled Core).
dev: bundle-core
    pnpm --filter @alpha/desktop tauri dev

# Build the Mac app with the current Core and install it as /Applications/Alpha.app.
# Launching it from the Finder asks once per build whether Alpha may read the Desktop folder
# (the runtime and resources still live in this repository); allow it.
app: bundle-core
    pnpm --filter @alpha/desktop tauri build
    rm -rf /Applications/Alpha.app
    cp -R apps/desktop/src-tauri/target/release/bundle/macos/Alpha.app /Applications/Alpha.app
    # The bundle in target/ would show up in Spotlight as a second "Alpha"; the installed copy is the app.
    rm -rf apps/desktop/src-tauri/target/release/bundle/macos/Alpha.app
    @echo "Installed /Applications/Alpha.app"
