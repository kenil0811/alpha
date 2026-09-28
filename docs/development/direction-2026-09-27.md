# Direction from 27 September 2026

Kenil restated what Alpha is for: one place where a non-technical person asks for a tool,
tracker, workflow or automation and gets something usable, editable and kept together with
everything else they asked for. The first requests the system must be able to build, not
hand-built:

1. a diet manager: log food by describing it, typing calories or picking a saved product; calories
   and macros worked out; an editable table; trends; goals; voice entry;
2. a fitness coach: plans from goals and equipment, exercise links, logged sets, progress;
3. a job hunt: watch configurable boards, score openings against a resume, track status, and
   later fill applications with approval.

## What changed

- The ticket/evidence process (`agent_handoff.py`, F-numbered checks, hashed evidence) is
  retired. Progress is Kenil running real requests through the assistant.
- The shell is rebuilt to the layout Kenil chose from Zazoo: a rail of modules, a module surface
  with tabs, and an assistant panel beside it (`apps/desktop/src/shell`, `modules`, `assistant`).
- The App contract has `views` and a declarative `screen` (`packages/contracts/alpha_contracts/screens.py`).
  The shell draws it; the builder declares it instead of compiling React. `ui.entry` remains for
  the rare custom screen. `tests/fixtures/apps/daylog_app` exercises every block.
- The builder prompt, `templates/app/APP_CONTRACT.md` and the app template lead with `screen`.

## Done on 27 September

- The diet manager request built and ran end to end through the assistant, builder and shell.
- `http` capability: `ctx.web.get` and `ctx.web.search` (public pages, DuckDuckGo search, per-run
  budget, private addresses refused), verified through the worker in a fixture module.
- `schedules`: declared in app.yaml, run by Core while it is open, shown on the module page with
  last and next run, on/off and Run now.

- The fitness coach request built first time ("Weekly Workout Coach", 58 checks, 15 minutes
  including a planner retry): it drafts a week from saved goals and equipment through the model,
  finds how-to links through web search, logs sets, and checks each morning for a missing week
  through a schedule. Fixed on the way: the planner now repairs a malformed plan once instead of
  failing the creation, and negated filters accept both spellings.

## Done later on 27 September

- Changing a module after it was made. A conversation started from a module's page carries
  `change_of`; the assistant sees a plain summary of the module and writes the brief for the
  whole module after the change; the creation rebuilds the same `app_id` from a writable copy of
  its current version, and only switches on if that version is still current. The record store
  accepts additive schema changes (new optional fields, wider choices) and refuses anything that
  would orphan saved records (`alpha/data/store.py: schema_change_problems`). Tests:
  `services/core/tests/test_change_module.py`, `tests/integration/test_creations.py`
  (`test_a_change_rebuilds_the_same_app_in_place_and_keeps_its_records`), and the shell's
  `continuity.test.tsx`.
- `ctx.web.get(...)` pages now carry `links` (text + absolute url), because the job hunt's first
  version tried to find listings with regexes over readable text and found nothing. The builder
  prompt and SDK reference say to read listing pages through `page.links`.
- The builder is told about the brief's recurrence and asked to declare a schedule; the job
  hunt's first version declared none although the brief asked for a check every four hours.
- Action forms start from the schema's defaults (the job hunt's "Active" switch defaulted to
  off on screen while the action assumed on), use the shell's button styles, and show a
  message-only result as one sentence.
- Third live request, the job hunt ("Job Search Watcher"): built in 15 minutes over two attempts
  (four date checks failed on the first). Profile, watched search and check all run; the check
  found no openings on a real board page (see the `links` change above), which is the first
  thing to fix through the new change flow.

- First live change (the job hunt's page reading) failed after three attempts and 27 minutes on
  a plan defect: the planner wrote `is_null` with no value and the record store refused the
  filter on every attempt. Now a valueless `is_null` reads as true, the planner's consistency
  check catches filter values the store would refuse (so the planner repairs the plan before
  anything is built), and a check that fails because the plan itself cannot be applied ends the
  build at once with reason `plan_defect` and a plain "try again" instead of burning repairs.
- The planner is told that web-reading actions cannot be checked against live sites and must not
  be pushed into fake inputs; the builder is told the web is unreachable during checks.

- Second live change of the job hunt succeeded: same module, new version, 44 checks, two
  attempts, records kept, the 4-hourly schedule declared and the test-only inputs gone. Its
  check still found nothing at first because the module's runtime profile carried a frozen copy
  of the SDK from before `links` existed. Now Core moves every active App onto the newest
  runtime profile at startup (`AppRegistry.move_to_profile`; the handlers must bind and the
  release must be unchanged, otherwise the App keeps its version), so a platform improvement
  reaches modules already made. After that the check saved four openings from the real page.
- What remains module quality, to be asked for as a change: the link filter keeps "Post a job"
  links and the search page itself lists one real job; a category page lists more.

- Kenil's first unassisted use: he pasted LinkedIn's landing page (not a search page) and pressed
  Check several times. Findings: the landing page yields category pages, not jobs; two checks
  raced over the same record and one failed on a revision conflict; drafting answers timed out on
  a 150-second model call. Core now refuses a second run of the same App action while one is in
  flight (409 with "already running, started N seconds ago"; `tests/integration/
  test_app_profile_sharing.py`). With a real LinkedIn search page the check saves 8 openings per
  run (the module's own cap; 52 more wait for later runs, which is slow and worth a change).

- Kenil's bar, after using the job hunt: a module should be what a capable product person would
  build for the request (sources added by name and resolved by the App, a detail page per
  thing, matching, freshness, quick filters), without the person spelling it out. The platform
  was telling every stage to do the opposite. Changed: the assistant's "keep the first version
  small" rule is now "complete first version, product-person bar, sources resolved by the App"
  with larger brief limits; the planner writes 3 to 6 scenarios; the builder is told the bar
  (detail per table, Added/last-read times, saved lists, batched model calls, sources resolved
  from a name with a web search fallback) and may use WebFetch/WebSearch during the build to
  look at the real sites it is writing a reader for; the build budget is 90 turns, 15 minutes
  per attempt, 40 in total. The screen contract gained `detail` on tables (the record's own
  page: fields, long text, Added/Last changed, actions) and the shell adds quick filters for
  every choice column a view can filter on. Tests: contract, shell (`screen.test.tsx`).

- Approved and built (evening): a module's own thread (Core lists the conversation that made a
  module and every change since at `GET /api/apps/{id}/conversations`; the assistant panel
  shows it when opened from the module and drops a conversation about something else); a
  speaking toggle (`apps/desktop/src/shell/voice.tsx`: click to listen, red and pulsing while
  it does, words land as they come, click again to stop; greyed with a dictation hint where
  the window cannot listen) in the assistant composer and quick entry; and Settings the
  person can change (`alpha/models/preferences.py`, `GET/PUT /api/settings`): the model for
  the assistant, the checks, building a new module, changing a module and modules' own model
  calls, plus steps, minutes per attempt, total minutes and repair attempts. Applied at the
  next use, no restart. The rail's New button now leaves the module page so a request there
  makes a new module.

- Proved the bar: the one-line request "I want a job tracker. I'm a senior backend engineer in
  London, open to remote. Watch LinkedIn and We Work Remotely for me", answered with defaults,
  produced "Backend Job Radar" in one build of two attempts (55 checks): four tables, sources
  added by name (typing "LinkedIn" found two listing pages and 80 openings; "We Work Remotely"
  three pages), a detail page per opening with the full description and match reason, first and
  last seen, status board, quick filters for status, work mode and match level, metrics, a trend
  and a daily 08:00 check. Its first check saved nothing because it asked the model for a list
  and the structured-call service refused `json` outputs; the service now accepts a bounded
  `json` field (64 KB, input up to 64 KB) and the fake route returns a list, so batch scoring
  works: the next check saved 21 openings from two model calls of about a minute each.
- Shell fixes from that session: an action's result spans the form (tables no longer collapse
  to one letter per line), and editing a cell no longer also toggles the row's detail page.

- Speed, evening: Kenil's change turn on the diet tracker ran past the 300 s limit on Opus.
  Measured: wait = output tokens / model speed (assistant 13k tokens 143 s, plan 22k tokens
  217 s). Now the assistant, the planner and modules' own calls default to Sonnet (Settings can
  change it), both prompts ask for tight output, and a thinking turn shows a clock, a "longer
  than usual" note at 90 s and a Stop button (Core kills the CLI process). The same change turn
  retried on Sonnet: 11k tokens in 103 s, briefed correctly.

- Quick changes (Kenil: "a simple change should not take 15 minutes"). A change request is
  triaged first (Sonnet, ~6 s): small edits inside what the module already has skip the brief
  and the plan; one structured call returns the changed files in full, identity lines are
  kept, the package must validate and bind, then it is switched on with the release guarded.
  Kenil's diet tracker request ("I don't want this log food box") through the new path: triage
  9 s, edit 72 s (Opus, 8.8k output tokens for a 14 KB app.yaml), live after 85 s with the form
  gone and data kept. The same request through the old path had timed out after 300 s at the
  assistant and then failed at the planner. Bigger changes still take the full path.

- Browser capability, level B (Kenil chose it over A alone). `workers/validator/src/
  browser_session.mjs` drives the installed Chrome (or the pinned Playwright Chromium): a
  visible window on a profile Alpha keeps under `data/browser/<site>` for the person to sign in
  themselves, headless reads of pages with scripts run (text, links, a sign-in-wall flag), a
  normal user agent so sites do not answer with a wall. `alpha/capabilities/browser.py` keeps
  the sites, per-module grants, pacing per site (pages per hour and a gap, in Settings) and
  every visit; the broker routes `http.get` through the browser for sites the module is allowed
  to read through the person's session (the module declares `browser`) and for `rendered=True`.
  Connections lists sites and starts a sign-in; a module's Settings has the switches; its
  Activity lists the pages opened. Read-only: the worker never clicks, types or submits.
- Agreed next: an in-app avatar assistant on every surface (Clicky-like), with a third verb
  besides build and change: run an existing module's action or view from a message, at once;
  same voice toggle; Kenil has character art. The floating desktop window waits for the Tauri
  host.

- Speed plan (Kenil: "go"). Done: (1) repairs as one edit call (`BuildService._quick_repair`,
  helpers in `alpha/builds/quick_edit.py`) before any new builder session; (2) on live routes the
  builder starts at once with the brief's examples as a preliminary plan while the planner writes
  the full checks (`CreationService._create_in_parallel`, `BuildService.submit(plan_later=)`,
  PLAN.md rewritten into the running attempt, verification waits); (3) behaviour scenarios run
  four at a time, each in its own preview (`CandidateVerifier._behaviour`); (4) the builder is
  told not to write or run its own tests and to finish when the module is complete. Still to
  do: (5) a fast lane for simple modules, and measuring a real build on the new path.
- Runtime profile drift: an SDK change (page links, then `rendered`, then link cards) needs
  `tools/build_app_profile.py` and a Core restart, or modules fail with a TypeError on the new
  keyword. Twice today. Automate: Core should publish a profile at startup when the SDK source
  digest differs from the newest profile.

- Late evening, from Kenil's own use: a `progress` block; display requests are never refused
  (closest block) but nothing is added unasked and a request that belongs to the shell
  (animation, colours, fonts) or is already the case comes back as a plain "nothing to
  change"; the triage reply promises no effect; a declined edit continues through the full path
  on its own; the updated card shows the one-sentence summary of what changed; goal bars
  animate in the shell. The assistant panel is closed on module pages by default and the rail
  folds to icons; both remembered.

- Speed item (5), the fast lane (late evening): a module that only keeps records (no web,
  browser, model calls or schedules) and is drawn by the shell is switched on as soon as its
  structural checks pass (package, dependencies, seal, handler binding), without waiting for
  the planner; its behaviour scenarios run right after, in the background, and the outcome is
  shown on the creation card and the module's page. When they find a problem, one click goes
  back: the previous version for a change (`POST /api/apps/{id}/revert`, a `reverted` release,
  records kept) or out of use for a new module (`POST /api/apps/{id}/remove`; nothing on disk is
  deleted). `CandidateVerifier.verify_structure` / `verify_behaviour`, `BuildService.submit(
  fast_lane=)` and `check_deferred`, the candidate's `checks` field, `GET /api/apps/{id}/checks`,
  Settings "Simple modules go live early" (on by default), module Settings "Go back to the
  previous version". Integration: `notes_screen` fixture variant. Also fixed: a change on the
  fake route starts on its own once briefed, so the fake builder's package now rides in the
  text as a `fake:` directive (the change integration test had been failing since auto-start).

- Avatar, Claude connection monitor and Settings sections (branch `feat/avatar-model-monitor`).
  The assistant's avatar is Bridge's Zazoo panda (rig and painted layers ported from the Bridge
  repository, the founder's own work; `apps/desktop/src/avatar/zazoo`), bottom-right on every
  surface, opening the assistant on a click. Its state is derived from real state only
  (`avatar/state.ts`): Claude unreachable, a failed turn/creation/recent run, waiting for the
  person, a creation running, a turn in flight, a module run, idle. Reduced motion shows a still
  head. Settings "Show the assistant's avatar" (`look.avatar`) and "Read replies aloud"
  (`voice.speak_replies`, the Mac's own voice). Settings -> Models now starts with the
  connection to Claude (`alpha/models/connection.py`, `GET /api/models/connection`,
  `POST .../check` for one tiny Haiku call, `POST .../login` for a supervised
  `claude auth login`): CLI missing, too old (decided by the flags Alpha passes that
  `claude --help` lists; 2.1.223 lacks `--permission-prompts` and `--restricted`, 2.1.283
  has them), signed out, last call failed, connected, with version, account, plan and the last
  successful call. A turn that fails because of the connection says so in the assistant panel
  with a link to Settings -> Models; an old CLI's "unknown option" is now `cli_too_old`
  instead of "no output". Settings has section links and an About card (what leaves this Mac,
  keyboard shortcuts). Not done: the floating desktop avatar window.

- Planner timeout (28 September, twice, a job-search request): the planner's structured call ran
  past 300 s (Sonnet, 23.8k output tokens of which 20.7k thinking; the same call at
  `--effort low` took 69 s and 7.5k tokens), the creation failed as `plan_unavailable` and the
  finished, structurally verified candidate was cancelled as `cancelled_by_user` although nobody
  pressed Stop. Now: structured calls take a reasoning effort (`--effort`, also in the
  connection monitor's required flags); the planner and change triage default to low, Settings
  -> Models has "Thinking for the checks" / "Thinking for sorting a change" (`effort.planner`,
  `effort.triage`: low, medium, high, Claude Code's default) beside their model pickers. When
  the planner fails in the parallel path and the brief's examples give at least one runnable
  scenario, the candidate is verified on those, switched on with its checks marked
  `preliminary` (the creation card and module page say so in one sentence), and the planner is
  retried once in the background (600 s); its full checks run after activation through
  `check_deferred(plan=...)` with the fast lane's one-click way back, or the checks stay
  preliminary with "Alpha couldn't write its full checks". With nothing runnable the creation
  fails with an honest sentence and the build is cancelled as `stopped_by_platform` (cause in
  the event). Tests: `services/core/tests/test_planner_timeout.py`, `workflows.test.tsx`,
  `settings.test.tsx`. Not covered end to end: the parallel path only runs on a live planner
  route, so no integration test drives it.

## Still to do

- Measured (23:16, "a simple reading list", records only): assistant briefed in 25 s with no
  questions; build 4 min 32 s, all of it the builder session on the CLI route (plan ready after
  45 s in parallel; structural checks under a second; switched on one second after the builder
  finished; 20 behaviour checks passed a second later). Typed request to usable module: 5 min
  13 s. What is left is the builder session itself: a faster model for new modules, fewer
  turns, or a smaller first version.
- The Mac app, started late on 27 September. The Tauri host (`apps/desktop/src-tauri`)
  builds and runs: `pnpm tauri dev --config '{"build":{"beforeDevCommand":""}}'` with
  `ALPHA_DATA_DIR=<diet-run>/data` reuses the running Vite server and the person's data;
  `pnpm tauri build` produces `target/release/bundle/macos/Alpha.app` (ad-hoc signed; data in
  `~/Library/Application Support/com.alpha.desktop`; runtime and resources still read from the
  repository). Found: launched from the Finder, macOS asks whether Alpha may access the
  Desktop folder (the repository lives there) and the host used to block on that prompt with
  no window; Core now launches on its own thread and the host logs to `logs/host.log`. Still
  to do: allow the prompt once (or bundle the runtime, F22), copy the person's data into the
  app's data directory or point the release build at it, sign and notarise, and the floating
  avatar window.

- Quick changes on Sonnet for the edit itself would be ~40 s (Settings: model for changing a
  module); the module's existing checks should run in the background after a quick change with
  a one-click revert.
- Model latency: one batch call takes 60 to 75 seconds on the CLI route; a faster route for
  modules' own calls (Settings already lets the person pick Haiku or Sonnet for them).
- The first block of a module's first tab must be a quick entry or form (verify rule); for
  modules whose main interaction is automatic this puts a manual form at the top. Relax it.
- A browser capability for sites that need a signed-in session.
- Module-quality changes to ask the job hunt for: skip "Post a job" links, clean titles, process
  more openings per check or score in one model call, refuse a page with no job links.
- Model call latency on the CLI route (7 to 9 s per small call, 150 s for a long draft) makes
  per-item model calls in modules slow; batch prompts or a faster route for App calls.
- Faster builds: tighter budgets for changes, re-run only the checks a change touches, a faster
  model for the assistant and planner, no separate plan-repair call.
- A render check for declarative screens (today only the contract validates them).
- Time to value: the target is a small module in under three minutes.
