# Decision: F08 creation, activation, the result surfaces and the G1 method

Date: 2026-09-26. Recorded by the coding agent (self-review). No bundle document is modified.

## 1. A creation is one Core-owned record per brief revision

`solutions/creation.py` drives this sequence: brief → acceptance plan → build → checks →
activation. The shell follows one `creations` row whose `stage` and `label` are already in the
person's words ("Deciding how to check it", "Building it", "Checking that it works", "Ready to
use").

- Starting twice for the same brief revision returns the running creation.
- A failure carries a plain message and a next step:
  - `revise` when the request needs changing (repair limit reached, an unsupported package);
  - `retry` otherwise.
- The failure lists up to three required checks that did not pass. A skipped required check
  counts, because it blocks readiness.
- A creation that was unfinished when Core stopped is marked `failed` with reason
  `core_restarted` on the next start. It is never revived, which matches how F02 treats builds.
- The brief, the plan, the build and its attempts, the Version, the release and the App's
  records are kept separately. The creation only references them.

## 2. The acceptance plan is written from the brief, before the build

`solutions/planner.py` makes one bounded structured call on the assistant route and gets back an
`app_name` and a `ValidationPlan`. The plan fixes the observable interface:
- action ids and inputs;
- collection and field names;
- for a screen, its visible labels.

It also says what counts as working: behaviour scenarios that read storage, one refused case,
and, only when the brief asks for `custom_ui`, a UI plan with sample data.

Before anything is built, the plan must pass three consistency checks:
- each `$ref` refers to an earlier step;
- every writing scenario reads storage;
- a screen is checked exactly when the brief asks for one.

The builder gets the plan as PLAN.md and implements to it. The platform verifies against its own
copy. On the fake route (control only), the plan is converted deterministically from the brief's
executable examples.

Whether an App gets its own screen follows the brief's surfaces. The template's screen is left
out of the workspace when the plan checks none. The fake builder follows the same rule, so a
screen that nothing verifies can never become ready.

## 3. The platform assigns the App's identity; the builder must keep it

- `app_id` is `app_slug(app_name, <6 characters of the creation id>)`, for example
  `notes-list-c7baa1`.
- The build targets it (`TargetProfiles.app_id`), and the fake builder rewrites it.
- The verifier's `package.identity` check fails a candidate that declares any other id, and
  passes (and is recorded) when the id matches.

Identity therefore never depends on what the model chose to write. The fake builder's
`--wrong-app-id` flag proves the refusal.

## 4. Activation is compare-and-swap on the current release

`Activation.expected_release_id` has three possible values:
- `None` means "this must be a new App";
- a release id means "replace exactly this";
- `ANY_RELEASE` is the F07 unconditional install (fixtures, the old build route).

A creation activates with `None`. `POST /api/builds/{id}/activate` accepts an optional
`{"expected_release_id": ...}`. A mismatch returns 409 and leaves the current release as it was,
so an old expectation cannot roll an App back.

The registry moved to `solutions/registry.py`, the Blueprint's `solutions/` package. It now
records, for each release:
- the Version's origin: `created`, `build` or `fixture`;
- the build id and verification report;
- the previous release;
- the creation.

## 5. Generated screens are served by the host from the sealed Version

The native host answers `alpha-ui://<app_id>/<version_id>/index.html` from
`data_dir/versions/<version_id>/dist/ui`, with the CSP the trusted UI build wrote (`index.csp`).
It serves a request only if all of these hold:
- both ids are well formed;
- the Version's `package.index.json` names that `app_id`;
- the file lies inside that directory.

The shell frames the screen with `sandbox="allow-scripts"`, which gives it an opaque origin. It
answers the screen's bridge with the App's declared grant: its views and UI actions, owned by the
current release. The frame never receives the session token.

A plain browser has no `alpha-ui:` handler. There the workspace says the screen opens in the
Alpha window, and the App's actions and saved data stay available.

## 6. The shell's result surfaces

- The navigation is **Assistant**, **My workflows** and **Activity**. The development fixture
  toggles appear only in a development build opened with `?dev`.
- The **creation card** shows the stages, a Stop button, the failure with its next step, and a
  ready card that says:
  - how many checks passed;
  - what is not connected;
  - how to open the result.

  Preview images are the checks' own screenshots. They are labelled "Preview", described as
  sample data, and followed by "Your own list starts empty". They are fetched with the shell's
  credential, and preview data never reaches the App's own store (integration test).
- The **workspace** opens an App with a screen in its own frame, and keeps actions and saved data
  under a disclosure.
- An App **without a screen** gets the actions view:
  - one form per action a person may run, derived from its input schema;
  - results in plain words, and a Stop button for long runs;
  - saved records per collection, with model estimates marked "(estimate)".

  Runs use origin `user` when the action allows manual use, and `ui` otherwise, which is what
  Core authorises.

## 7. Host and build environment

The desktop host now passes:
- `ALPHA_PLATFORM_RESOURCES`: in development, the repository;
- `ALPHA_NODE`: the Node 24 keg;
- `ALPHA_UI_BROWSER`: the pinned headless shell, when present.

The host still honours `ALPHA_DATA_DIR` and `ALPHA_RUNTIME_DIR` only in debug builds. While the
build queue works, Core holds `caffeinate -i -w <core pid>`. The assertion ends with the queue,
or with Core if Core dies, so the Mac cannot sleep through a build (found live in F07).

The capability catalog now lists these as available, with their operation names:
- records;
- artifacts;
- models;
- custom UI.

`/api/capabilities` also reports the installed profile versions. A release Vite build leaves out
the development qualification pages and uses Vite's default minifier. The `esbuild` minifier it
named before is not installed with Vite 8, so release builds failed.

## 8. G1 is run on frozen code, through Core's shell routes, on its own data

`evals/g1.py` starts Core exactly as the native host does: the same environment and routes. It
runs from a git worktree of the freeze commit, with that worktree's own `.alpha-runtime` and a
dedicated data directory. The person's running Alpha and later edits in the main checkout cannot
change what G1 ran on. For each request it:
1. starts a conversation and answers questions with the product's "use sensible defaults",
   unless an answers file is given (recorded either way);
2. creates the result;
3. records the prompts, questions, brief, plan, every attempt and its generated source, the
   reports, screenshots, usage, estimated cost and latency.

Primary use works in one of two ways:
- **An App with a screen:** its sealed screen is driven by `evals/g1_screen.mjs` in the pinned
  headless browser. The driver uses the same bridge host package and the same grant as the
  shell, and its requests go to the real Core, so the records are the person's own.
- **An App without a screen:** its actions run as the actions view runs them.

`reopen` starts a fresh Core on the same data and checks each App's identity, records and screen.
`share` covers C04 on two generated Apps: while one run is cancelled and the other finishes, it
compares their processes, scratch directories and records.

The founder's M1 review opens the same data directory in the Alpha window. The headless drive is
evidence of use through the generated screen; it does not replace the native window.

## Remaining, stated plainly

- `POST /api/runs`, the synthetic worker used by the runtime fixture and the integration tests,
  is still served. The shell reaches it only through the development fixture. F22's release
  configuration should drop it.
- Only brand-new Apps are created. Changing an existing App (a new Version replacing its current
  release) uses the compare-and-swap above, but has no user flow until F10.
