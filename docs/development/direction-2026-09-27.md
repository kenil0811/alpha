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

- 28 September, early morning: the Mac app took over the person's data (`diet-run/data` copied
  into `~/Library/Application Support/com.alpha.desktop`; `/Applications/Alpha.app` installed;
  `just app` bundles Core, builds and installs). The third verb, do: `alpha/assistant/acting.py`
  (`POST /api/act`): one Sonnet call maps a sentence to a module's action, view, tab, a change
  or a new build, Core runs it at once, a second short call says what happened (1.7 to 3.3 s to
  decide, about 3 s to phrase). The desktop avatar: a transparent always-on-top Tauri window
  (`avatar`) with a placeholder character (`apps/desktop/src/avatar`), a panel that grows from
  the bottom-right corner, the same voice toggle, handoffs to the main window through shared
  storage (open a module or a conversation), a tray item and a Settings switch. Verified live
  in the installed app: "open the backend job radar" opened it in the main window; "how many
  books have I finished this year" read the reading list; in the browser shell "how many
  calories have I eaten today" and "log two boiled eggs" ran the diet tracker's view and
  action (the eggs were saved with a model estimate). Known: every rebuild of the ad-hoc-signed
  app re-triggers the macOS Desktop-folder prompt on a Finder launch (allow once per build; a
  terminal launch inherits access); the bundled runtime must be re-synced (`just bundle-core`,
  part of `just app`) after any Core change or the app serves stale routes.

- 28 September, evening: Kenil asked the avatar to "fill in some mock data in my diet
  tracker for the past 10 days". The single-shot verb routed it to a new build, the assistant
  refused, and the avatar then claimed twice to be "still working". Replaced with a step loop
  (`ActService.act`): each step one model call over the modules, FACTS (runs in flight,
  creations in progress, what earlier sentences actually led to) and this sentence's
  observations; a step runs a batch of actions (up to 40), reads a view, opens, changes,
  builds, or finishes with a reply written from the observations. Verified: 22 entries over
  ten days through `log_entry`, reported as such. Rule kept: a claim of progress is allowed
  only when FACTS show something running.

- 28 September, evening, after the decisions of the day (see
  ~/.claude memory "Direction 2026-09-28"): derived pages. Every collection is a page Alpha
  draws (`apps/desktop/src/modules/DataPage.tsx`): table first with sort, search, filters on
  choice and status fields, hide done, edits in place, an add row, a record panel, saved lists
  (kept per module in the shell); board (drag between status columns), list, calendar and
  chart a click away. New field kinds `long_text`, `status` (with `done_choices`),
  `multiselect`, `url`; `CollectionSchema.title_field` and `page` (opening view, group and
  date fields, sort, columns, quick entry); `AppSource.summary` cards (metrics, progress,
  trend, text) as the Summary tab. A module's tabs are Summary, any custom Screen, declared
  screen tabs, one page per table, and Actions when nothing else offers manual actions; the
  Data section is gone. A module with tables counts as having a screen (no primary action
  needed). A declared screen tab that already lists a table stands in for that table's page.
  Any error that escapes the shell's rendering is shown in the window with a reload. Builder instructions, APP_CONTRACT.md, the template and the default conventions now
  say: declare tables well, do not design screens. Existing modules keep their screens and gain
  the pages.

- 28 September, late: profile facts and context packs. `alpha/context/profile.py` keeps
  append-only facts about the person (field, value, provenance person/module/assistant/
  inferred, source, confidence, state accepted/suggested/rejected/retracted, supersedes); a
  correction is a new fact, forgetting retracts. Modules get `ctx.profile` (the `profile`
  capability: get/all read accepted facts, set records what the person typed, suggest waits for
  a yes). `GET/POST /api/profile…`; the shell's About you page lists facts with their source,
  takes suggestions' yes or no, corrects in place and forgets. `alpha/context/pack.py` assembles
  a pack for every assistant and avatar turn: accepted facts, the modules with counts, records
  that match the sentence's words (a bounded contains-search over text and choice fields, most
  recent first), recent activity; each line names its source. The assistant prompt gained rule
  9c (build on what is known, never ask for it again, name the module a fact came from).

- 28 September, later: connections and relations. A module declares `uses:` (another
  module's id, the views it reads, a purpose in the person's words) with the `connections`
  capability; `alpha/context/connections.py` keeps a switch per use (on when declared, the
  person can turn it off in the module's Settings), reads go through the source module's
  declared views (`ctx.modules.available/query/get`, broker `modules.*`), nothing is copied. A
  `relation` field kind (module + collection) stores another module's record id; the page
  shows its title and offers a picker (`/api/apps/{id}/related/…`). The verifier checks that
  used modules and views exist (`package.connections`); the builder's notes list the person's
  other modules with their views and fields. Also: hidden columns are remembered instead of
  shown ones, so a field a module gains later appears on its own.

- 28 September, night: the researching assistant. (1) First steps: five short questions on
  Home (`FirstSteps`), answers become accepted profile facts, one model call proposes two or
  three modules to begin with, each a request sentence to send (`alpha/context/onboarding.py`,
  `/api/onboarding`). (2) Research before the brief: when a new-module brief is complete and no
  question is left, the conversation goes `researching` (`alpha/assistant/research.py`: two web
  searches for how such a tool is shaped, the first hit and any named source read, 45 s, all
  fenced as data), then a proposal call gives two or three shaped options with a default and
  the evidence behind them; state `proposed`, the shell shows a card, the choice is a normal
  reply and becomes the brief; once per conversation, never for changes or answers. (3) Weekly
  nudges: `alpha/context/review.py` reads the context pack once a week (and on request),
  writes at most three observations with a next step, shown on Home under "Alpha noticed",
  each a request away or dismissed.

- 28 September, late night: standalone skills, the Intelligence page, column order and widths.
  (1) Skills (`alpha_contracts/skills.py`, `alpha/context/skills.py`, `/api/skills…`): a
  reusable ability outside any module: title, what it does, how Alpha does it (a procedure in
  plain steps, or a module action), the inputs it needs, what it produces, the sources it may
  read. A procedure runs as a bounded step loop (search, read a page, read one of the person's
  modules, done; 8 steps, 150 s) with fetched text fenced as data and the items taken only
  from what was read; every run is kept with its evidence. The avatar's step loop has a
  "skill" step and sees the catalogue; a module reaches skills through `ctx.skills`
  (`skills` capability, ops `skills.list` and `skills.run`; only procedure skills, so a module
  never waits on a skill that would call back into a module). (2) Intelligence (rail item,
  `shell/Intelligence.tsx`): Second brain (the facts, what each module keeps), Skills (list,
  make, run with inputs, results table with sources, retire), Automations (every schedule
  across modules, switchable) and Connections (every module-to-module read, switchable; a
  link to accounts and sites). (3) Derived pages: columns can be moved from the ⋯ menu and
  resized by dragging the header edge; order and widths are remembered per table. The record
  panel is the form view.

- 29 September, morning: the lean build pipeline, after a 91-minute failed creation
  (build_2349017e: lid closed for 62 of them; then invalid YAML, an invalid board, and two
  model-unavailable checks judged too strictly; plus my broker bug where `connections` never
  unlocked `modules.*`). Fixed the judge and the broker first. Then, by subtraction: (1) every
  attempt gets a `./validate` script (`alpha/builds/validate.py`: app.yaml parses and matches
  the contract, layout, compile, every handler resolves, from the verifier's own code) and the
  builder is told to run it before handing over, so a typo costs seconds, not a repair round;
  (2) the fast lane is every module Alpha draws (only a custom compiled screen waits for the
  full checks): structure decides activation, the independent plan's checks run while the
  module is in use, revert stays one click; (3) repairs: the fixed allowance plus one more
  while the failing count shrinks (`RepairPolicy`), bounded by the time budget; (4) the failure
  card says what happens next in plain words and no longer lists check names. Still to do from
  the same discussion: a failed deferred check should start a quick repair on its own rather
  than only a notice, and a build paused by sleep should say so.
  Measured on Kenil's own request right after (build_731b6f1f, "Track job search cold calls",
  http + browser + models + connections, 5 plan scenarios): builder 6 min 29 s including three
  `./validate` runs (11 problems, then 6, then OK, within two minutes of starting); switched
  on 0.6 s after the builder handed over; 26 behaviour checks passed 0.5 s later. Typed to
  usable: 6 min 30 s, first attempt. The same request had failed the night before after 91
  minutes and three attempts.
  Also brought the integration suites (assistant, creations, shell journey, shell probe) up
  to the proposal flow and the derived pages, which the 28 September slices had left behind:
  147 integration and 8 UI tests pass.

- 29 September, midday: pages, not screens. Kenil's cold-call module came out with a
  declared `screen:` (form + table blocks, the old shape) on top of `page:` and `summary:`,
  so the module page showed the poorer screen tables and hid the standard pages we decided
  on. Cause: the builder's own instructions in the Claude CLI harness still said "the screen
  is declared under screen:" while the contract document and conventions said pages. Fixed
  by one rule in one place (`alpha/data/packages.py: screen_page_conflicts`): a screen never
  draws a table, board or list over a collection; the verifier's `package.screen` and the
  builder's `./validate` both apply it; installed modules from before keep their screens.
  The harness instructions now say: describe the data (`title_field`, status, `page:`,
  `summary:`), do not design a screen; `screen:` only for what a page cannot give. The
  contract document's screen section and the notes_screen fixture follow.

- 29 September, afternoon: projects and sessions, after Kenil's "refresh the job applications"
  turned into a rebuild (the panel could only start build conversations) and his question about
  threads and projects ("this can make or break my whole system"). Researched first: Hindsight,
  mem0, Zep/Graphiti, Letta, LangGraph, Claude Code's memory, the Claude Projects redesign of
  17 September, ChatGPT Projects, OpenClaw, three 2026 papers and an independent benchmark
  (sources in the memory note "Sessions and memory design"). Findings that decided the shape:
  every memory library needs an embeddings model plus an API LLM plus a database, and Alpha
  has neither embeddings nor an API key (its route is the Claude Code CLI); verbatim retrieval
  beats fact extraction (arXiv 2601.00821); a simple baseline matches mem0 and Zep (arXiv
  2511.17208); mem0's open-source edition scored 32–49% on LongMemEval independently against
  93% claimed; the two big products both landed on projects with a shared memory and many
  threads. So: no library, no embeddings, no knowledge graph.
  Built: **projects** (`alpha/context/projects.py`: name, goal, Alpha's notes, at most one
  project per module, never required); **sessions** (`alpha/assistant/sessions.py`: a durable
  chat in a project or global, an optional focus module, every turn kept verbatim in SQLite
  with an FTS5 index, a rolling summary, and compaction in one call that folds the oldest turns
  into notes, refreshes the project's notes and *suggests* facts the person accepts on About
  you or the project page); **the one loop** (`alpha/assistant/acting.py` is now the turn
  handler for every message: run, read, use a skill, open, change, build, or answer; a build or
  change is a conversation that becomes a card in the session; typed text goes to a
  conversation waiting on the person, or to a brief nothing has been made from yet); **scoped
  facts** (`profile_facts.scope`: `person` or `project:<id>`); the context pack leads with the
  project's facts and modules; a module made in a project's session is filed under that
  project (`CreationService.on_made`). The avatar's flat `act_turns` became the global "Quick
  asks" session (imported once); `/api/act` still answers it. Routes: `/api/projects…`,
  `/api/sessions…` (`/messages` with `wait`, `/search`, `/compact`), `/api/apps/{id}/project`,
  `?scope=` on `/api/profile`. Shell: the rail groups modules under their projects; a project
  page (goal, Alpha's notes, modules, sessions, project facts); the panel is a session with a
  switcher and "New session", opens on the scope's latest session (remembered per place), draws
  conversations as cards (`assistant/ConversationCard.tsx`), and keeps a module's earlier
  requests reachable. Verified in the browser shell against a scratch Core on the fake route:
  a global session answered; a build card opened from a message; a project made, renamed in
  place, a module filed and nested in the rail; a project session ran "open" with the outcome
  line; the module page's panel picked the project's session; the avatar route, listing and
  search over the API. Tests: `test_sessions.py` (9), acting and skills updated, 155 core, 91
  shell, assistant/creations/shell-journey integration suites green.
  Still to do from the design: an idle-time consolidation pass (today compaction runs by
  size only); Alpha proposing a project when a module is made from a global session; "Quick
  asks" pointable at a project; session-level Stop; embeddings later behind the same search
  interface. Then the failure-ownership design (recorded calls, undo on failure, repair cases).

## Still to do

- Assistant: the person's own words for "your call" and "ask me fewer questions"; research
  through the signed-in browser for sources that need it; nudges that link to the module.
- Connections: the second brain graph over relations; a module reading another's aggregate
  views in its summary cards; asking before a brand-new module reads an existing one.
- Profile: the five-question first conversation that seeds it (with the research stage); a
  "why does Alpha think this" trail per fact; the assistant recording facts it learns in
  conversation as suggestions.
- Derived pages: a records view of saved lists shared with the assistant; dragging columns
  directly (today: arrows in the menu); grouping in the table view.
- Skills: the assistant teaching a skill from a conversation ("remember how I do this"); a
  skill that runs on a schedule; a skill's items saved into a module in one step from the
  results table; per-module Intelligence tab.
- Avatar: Kenil's own character art and emotes; a floating window that follows Spaces is done,
  a hotkey and a bubble that speaks replies aloud are not; the main window's assistant panel
  should get the same "do" verb.
- Sign the app with a stable identity (or bundle runtime and resources, F22) so macOS stops
  asking for folder access after each build.

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
