# Decision: F05 App worker channel, default runtime profile and install path

Date: 2026-09-25. Recorded by the coding agent (self-review). No bundle document is modified;
these are implementation choices inside the bundle's rules, recorded because later tickets build
on them.

## 1. App workers reach capabilities over their supervised pipes, not loopback HTTP

The Capability Protocol requires an authenticated workload token and Core-supplied owner for
every call; it does not fix a transport. App workers write one JSON call per line on their
original stdout and read replies on stdin. Every call carries a per-run token that Core issued in
the job line (stored only as a SHA-256 hash, revoked when the run ends and on Core restart), and
Core accepts it only on the pipe of the run it was issued to.

Why: an App worker needs no network path to Core at all, so F20's OS sandbox can deny all network
to generated code; a leaked token is useless on any other pipe (tested); no port or session
token is ever visible to generated code. Anything a handler prints goes to stderr, so it cannot
forge protocol messages (tested with 4,000 forged lines).

Consequence: calls from one worker are sequential. A long model call holds that worker's
channel until it returns, which fits the one-action-per-process model. A future long-lived
worker would need concurrent call IDs, which the message format already carries.

## 2. The default App/Task profile contains the SDK and worker only

`pyprof-…` = the pinned uv-managed CPython 3.13.9 plus two wheels built from this repository
(`alpha-sdk`, `alpha-app-worker`), installed with `--require-hashes --no-deps --no-index` and
compiled bytecode, sealed read-only. No third-party package is in the closure. Timezone data comes
from macOS's system zoneinfo, which the isolated interpreter reads correctly.

Why: the smallest closure that satisfies the F05 contract; every artifact hash is recorded;
hatchling wheels are reproducible, so the same source always yields the same profile ID.

Consequence: timezone rules follow the macOS version. Adding `tzdata` (or any module a real
request needs) produces a new profile identity through the same tool and requires qualification
per Implementation Blueprint §10.

## 3. Profiles are published by the trusted build path; Core only verifies

`just bundle-core` runs `tools/build_app_profile.py`, which stages, installs, validates, seals and
atomically publishes into `<runtime>/profiles/<profile_id>`. The host passes that directory as
`ALPHA_PROFILES_DIR`. At startup Core recomputes the manifest digest, lock and wheel hashes, the
installed-tree digest and the base interpreter hash, then registers the installation `ready` or
`quarantined`. Core never runs uv or pip; in tests it is started with no `PATH` at all.

Consequence: F22 replaces the development runtime directory with the signed relocatable bundle;
profile identity and verification stay the same. Deleting profiles (leases, journal) is F22.

## 4. Core validates action schemas with jsonschema 4.26.0

Action inputs are checked before a Run exists and outputs before a Run can succeed, in trusted
Core, against the Draft 2020-12 schemas declared in `app.yaml`. Added `jsonschema==4.26.0` (and its
pinned closure) to Core only; generated code never sees it. Record values use the platform's own
field specs, not JSON Schema.

## 5. F05 installs Apps from fixture directories only

`POST /api/dev/fixture-apps/{name}/install` is enabled only when the host sets
`ALPHA_DEV_FIXTURE_APPS_DIR`, and the desktop host does not set it. It performs the real sealing
and handler resolution path. F08 connects verified builds to the same `AppRegistry.install`. The
release row it writes is a minimal pointer for run ownership; activation with
expected-current-release checks is F08, schema migration is F10.

## 6. Record pages use opaque offset cursors bound to the query

A cursor encodes the query digest and an offset, so it cannot be reused with a different query.
Under concurrent writes a page can shift. F09 owns concurrency proof and may move to keyset
cursors without changing the SDK surface.
