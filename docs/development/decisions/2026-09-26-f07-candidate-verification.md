# Decision: F07 candidate verification, previews, the render check and bounded repair

Date: 2026-09-26. Recorded by the coding agent (self-review). No bundle document is modified.

## 1. One package path for every Version

Builder candidates and development fixtures go through the same code (`data/packages.py`):
- the App contract and file rules;
- dependency resolution against profiles re-verified on disk;
- the trusted UI build;
- lock provenance and content-addressed sealing.

The F02 build path had its own package format, digest and a candidate runner on Core's
interpreter. All of that is removed. A ready candidate is therefore byte-for-byte the Version that
activation installs. Activation re-verifies the bytes and the profile manifests first.

Package Layout names `dependencies/uv.lock` and `dependencies/pnpm-lock.yaml`. The profiles'
actual lock files (`requirements.lock` for Python; `package.json` and `pnpm-lock.yaml` for UI)
are copied instead as `dependencies/python/…` and `dependencies/ui/…`, under their real names.

## 2. Checks run in an isolated preview, not in the person's platform

Each behaviour scenario, and the render check, gets a fresh preview (`builds/preview.py`). A
preview has its own control store, record and artifact stores, broker and run coordinator. It
shares only the worker supervisor, the profile inventory and the model gateway.

Actions therefore run through the real path: the same App worker, profile and broker, with
per-run tokens. Nothing from a preview appears among the person's Apps or runs. This answers
"preview cannot be mistaken for an activated working release" structurally, not with a label.
Persistence is judged by reading the preview store directly, never from the candidate's output.

## 3. The validation plan is written before the build and never by the builder

A `ValidationPlan` (contract 0.2) has two parts:
- **Behaviour scenarios:** run actions, then check stored records. `$ref` and `$today`
  placeholders let steps use earlier outputs and today's date.
- **An optional UI plan:** the primary interaction addressed by visible labels, the record it
  must save, and the text it must show, plus sample data created through the App's own actions.

The builder receives a readable copy as PLAN.md. The platform verifies against its own stored
copy. F02's `acceptance_examples` still work, converted into exact-output scenarios. F08 must
derive plans from the brief. A UI plan names labels, so the brief must fix them.

## 4. The render check: Playwright 1.62.0 driving the headless shell it pins

`workers/validator/src/ui_check.mjs` is a trusted Node worker. It loads the sealed
`dist/ui/index.html`, with its own content security policy, in a frame sandboxed to scripts only.
The frame sits on a harness page that runs the real bridge host from the UI build profile.

Playwright answers both virtual origins from disk, so there is no network or server. Bridge
requests reach Core only over the worker's pipes, and only within the screen's declared grant.
The relay is exposed to the harness page alone, never to the App frame.

The check passes the screen through these states:
- **Empty:** a page title, no error, no script errors, no sideways scroll at 768px.
- **Primary interaction:** it must invoke a declared action, and the record must really be
  stored.
- **Populated:** sample data comes from the App's actions; text is shown and the layout checked.
- **Failed read:** an error must be shown, not an empty screen.
- **Failed save:** an error must be shown and nothing stored. Kept input is advisory.

Screenshots of every state are retained with the report.

Browser: `playwright-core` 1.62.0 pins Chrome for Testing 151.0.7922.34
(`chromium_headless_shell-1234`). The binary already sat in the standard Playwright cache on this
Mac, put there by another project, so nothing was downloaded. Core receives its path from the
host (`ALPHA_UI_BROWSER`), and the report records the browser version. Without it, UI candidates
cannot become ready: the check is required and would be skipped. Installing it on another Mac:

```bash
pnpm --filter @alpha/validator exec playwright-core install chromium-headless-shell
```

F22 bundles it with the app.

## 5. Bounded repair, and what "failed" means

- A harness that reports failure stays failed, and its package is still verified for the record.
  Harness errors, timeouts and cancellations are not repaired.
- A claimed candidate that fails required checks gets a repair request while all limits allow:
  - **Repairs:** at most `max_repair_attempts` (2).
  - **Time:** 12 minutes per attempt, 30 in total, including verification.
  - **Money:** the cost limit, where the route is metered.
- The repair request (REPAIR.md) holds every failed check with its evidence and screenshots.
  It goes into a fresh workspace seeded with the previous package.
- When the limits stop repair, the terminal reason names the limit. The failure category still
  names what was wrong, for example `validation_failed` or `dependency_unsupported`.

## 6. Dependencies outside the profile

A module declared in `app.yaml`, or an import outside the standard library, the SDK and the
package, fails the candidate. It becomes a durable qualification request in `dependency_requests`,
listed at `/api/dependency-requests`. No shared environment is touched.

Platform internals, installers (`ensurepip`, `pip`, `venv`, `setuptools`) and computed dynamic
imports are refused. A profile whose worker cannot scan imports, meaning one built before F07,
fails verification rather than skipping the scan.

## 7. Reproducible live repair: seeded first attempts (qualification only)

A live builder's first attempt usually passes or fails unpredictably. F07.C03 needs a real repair
of a reproducible case, so a build may start from a named known package (`seed_package`). This
works only when the host sets `ALPHA_DEV_SEED_PACKAGES_DIR`, which the desktop host never does.

Seeding changes only where the first candidate comes from. It is verified like any claim, the
attempt records the `seeded` harness, and every repair is done by the build's real route.

## 8. Host configuration F08 must supply

Builds need three things from the host:
- **Platform resources** (`ALPHA_PLATFORM_RESOURCES`: the template, references, UI build tool
  and render check);
- **The pinned Node** (`ALPHA_NODE`);
- **The pinned browser** (`ALPHA_UI_BROWSER`).

The desktop host does not set these yet. The shell cannot reach builds until F08, which wires
both together.
