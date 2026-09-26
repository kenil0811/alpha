# M1 review

**Status: M1 repair in progress. M1 is not accepted.** The founder's external review
(`../m1_review/Alpha_M1_Review.md`, 26 September 2026, revision 2) keeps the foundation but does
not accept M1 as a usable creation experience. It reports 13 findings, F01–F13; these are the
reviewer's labels, not the ticket ids. It also hands over a bounded repair plan, M1-R00 to
M1-R07.

Scope is unchanged:
- the original tickets F01–F08 only;
- the Claude CLI subscription route and the existing stack stay;
- F09–F24 stay deferred.

The founder gave the go-ahead to start, including screen control for native checks (chat,
26 September 2026).

This file carries the repair log. The first M1 packet is kept below, unedited, as history. Its
completion claims are withdrawn: see the check audit.

## M1 repair log

### M1-R00: baseline (26 September 2026)

**Starting point**
- Repository `main` at `d8c8f03`. Its platform code equals the G1 freeze `f7dada6`; only the
  G1 eval driver (`4b2c77a`), one test and documentation differ.
- Toolchain: uv 0.12.17, CPython 3.13.9, Node v24.21.0 (Homebrew keg), pnpm 10.34.5,
  rustc 1.98.1, Tauri CLI 2.11.5, just 1.58.0, Claude Code 2.1.278.
- Profiles in the G1 freeze: runtime `pyprof-391f9ca6e9db5bc54576`, UI
  `uiprof-5a3bad2e0741affeb06b`.
- The main checkout's `.alpha-runtime` is stale (built 2026-09-25). It holds
  `pyprof-48e953297d79b3ac3547` and four older UI profiles. Repair work rebuilds it with
  `just bundle-core`.

**Launch paths in use**
- The G1 demo: the frozen worktree `../alpha-g1` at `4b2c77a`, launched as
  `ALPHA_DATA_DIR=../g1-run/data …/alpha-g1/…/Alpha.app/Contents/MacOS/alpha-desktop`. It was
  open at the time of this baseline (pid 39072) and is left untouched.
- Repair work: the main checkout, on its own data directories, run natively with `just dev` or
  the debug bundle. A Vite/browser window is not accepted as native evidence.

**Native delivery starts unverified.** Generated-screen delivery in the Alpha window
(`alpha-ui://`) has never been observed, whatever earlier completion flags said.

**Check audit.** Each check is judged against the findings and the repair mapping in the
review's handoff. A reopened check returns to `pending` until fresh evidence exists. A kept
check keeps its original evidence file and hash.

| Check | Was | Now | Why |
|---|---|---|---|
| F01.C01 native | passed | kept | Bootstrap with bundled Python and reopen are unaffected by the findings. The R07 native session will exercise them again. |
| F01.C02 native | passed | **reopened** | Finding F13: Stop can leave a record that says "cancelled" while activation proceeds, which contradicts honest durable cancellation state (R03). |
| F01.C03 integration | passed | kept | IPC credentials and origins are unaffected. |
| F01.C04 native | passed | **reopened** | Findings F02 and F06: interrupted and in-progress work is not restored in the shell after navigation or restart (R01). |
| F01.C05 integration | passed | kept | Locks and exact versions; `just verify-locks` runs again at the final freeze. |
| F02.C01–C04 | passed | kept | Builder route, failed-candidate rejection, cancel cleanup and secret handling are unaffected. The ticket status returns to in progress only because F01 did. |
| F03.C01 native | passed | kept | UI authority separation stands. R03 renews sessions only through the trusted host. |
| F03.C02 integration | passed | **reopened** | Finding F10: session lifetime and renewal change. Stale or revoked authority must still fail (R03). |
| F03.C03 native | passed | kept | Sandbox probes are unaffected. |
| F04.C01 live_model | passed | **reopened** | Finding F11: the assistant claimed "nothing leaves this Mac" on a remote route. Finding F12: artifacts were advertised as deliverable (R02, R04). |
| F04.C02 integration | passed | **reopened** | Finding F07: a correction after activation silently creates a second App (R04). |
| F04.C03 rendered_ui | passed | **reopened** | Findings F01 and F06: shell layout, and no Retry or Start over after a failed turn (R01). |
| F05.C01 integration | passed | **reopened** | Mapped to R02: model-failure outcomes and provenance must be re-verified through the SDK. |
| F05.C02, F05.C04 | passed | kept | Refusals, bounds and profile sharing are unaffected. F08.C04 covers sharing again. |
| F05.C03 integration | passed | **reopened** | Finding F04: a generated App presented an invented number as a model estimate (R02). |
| F06.C01–C04 | passed | **reopened** | Finding F09 and the Form and refusal issues: kit changes need a new UI profile, which must qualify again (R05). |
| F07.C01 integration | passed | **reopened** | Finding F05: acceptance lacked model-failure and deterministic-outcome assertions (R02, R06). |
| F07.C02 rendered_ui | passed | **reopened** | Finding F05: keeping typed input after a failed save was only advisory, and layout composition was not assessed (R05, R06). |
| F07.C03, F07.C04 | passed | kept | Live repair and dependency integrity are unaffected. |
| F08.C01–C04 | passed | **reopened** | Finding F05: G1 bypassed the real shell and the native window, and the G1 verdict had a false positive. All four need a fresh G1 (R07). |

With the reopened checks, F01 and F03–F08 go back to in progress. F02 keeps its passed checks
but can't be complete while F01 isn't.

### M1-R01: shell layout, continuity and recovery (done, 26 September 2026)

The shell now has:
- one working column;
- the conversation kept across navigation and reopening;
- Recent requests, and **Being made** under My workflows;
- polling that recovers from failures;
- Try again and Start over after a failed turn;
- a startup reconcile for turns cut off by a restart.

The native session confirmed each of these, and also saw a generated screen render and save
through the bridge inside the Alpha window for the first time. It found four more shell issues,
all fixed: double scrolling, a wrong blocked-request message, fixture wording in Activity, and
technical ids on screen. Evidence: `docs/development/evidence/M1-R01.md`.

Original checks F01.C04, F04.C03, F08.C02 and F08.C03 stay pending until the final freeze.

### M1-R02: truthful data and provider claims (done, 26 September 2026)

**F04.** A failed model estimate can no longer pass as a saved number:
- a required `model.failure.<action>` check runs every model-using action with the model
  unavailable, malformed and timed out;
- plans can make the model fail on purpose;
- `null` means unknown.

**F08.** "Unknown is not zero" is now in the App contract, the builder rules and the planner
rules. The deterministic calorie assertions run in M1-R07.

**F11.** Data-location statements come from the configured routes: DATA FACTS in the assistant
prompt, turns grounded before they are stored, and "Where your data goes" in briefs and
workspaces.

Evidence: `docs/development/evidence/M1-R02.md`.

### M1-R03: cancellation and session lifetime (done, 26 September 2026)

**F13.** Stop and switching on are conditional transitions in one serialised store:
- an accepted Stop prevents any release;
- a Stop that arrives after switching on began is refused with the true reason;
- a build submitted while Stop landed is cancelled.

**F10.** An expired generated-screen session is renewed, without replaying the request, only
while the App's release and grant are unchanged. A change ends the session, and the screen keeps
what the person typed.

Evidence: `docs/development/evidence/M1-R03.md`.

### M1-R04: usable outputs and honest scope (done, 26 September 2026)

**F03.** An App without its own screen has one clear form: its declared `primary_action`, which
verification requires. It takes multi-line and list inputs, shows readable tables and lists (no
JSON), and keeps helper steps internal. This was tested on the real G1 held-out manifest.

**F07.** After an App is made, the Assistant offers "Create a separate workflow" and says that
changing the App isn't available yet. Corrections wait while a creation runs.

**F12.** File delivery is marked unavailable until F11, and the example prompt is replaced.

Evidence: `docs/development/evidence/M1-R04.md`.

### M1-R05: shared interaction quality (done, 26 September 2026)

**The chart.** The trend chart is a fixed 160 px with 12 px lettering at 1002 and 670 px. The old
one measured 2,488 px tall with 171 px lettering. It also shows coverage ("Days with entries").

**The kit form.** It enforces required fields, returns focus for the next entry, and keeps the
draft after a failed save. Refusals are shown in the App's own words.

**The render check** now requires:
- the main interaction visible without scrolling in Alpha's workspace;
- repeated entry;
- a kept draft after a failed save.

The kit ships in the next UI profile, and existing sealed profiles are unchanged. Evidence:
`docs/development/evidence/M1-R05.md`.

### M1-R06: trustworthy acceptance (done, 26 September 2026)

**The G1 verdict** judges each call against records read before and after it. An expected
refusal must fail (or be refused), give the stated reason, and change nothing. The review's
false positive now fails. `reopen` actually re-runs its action.

**The platform verifier** applies the same rule to its own expected-failure steps. A handler
that saves and then refuses was made ready before; now the build fails.

**Plans must cover the brief:**
- every action runs;
- computed results are checked with fixed values;
- model steps are also run with the model unavailable;
- stored data is read back.

An incomplete plan is rewritten once, or planning stops with the gaps named.

**The real shell is driven end to end in a browser:** create, use, a refusal, reload and
Activity. That run found a naming mismatch on the ready card, now fixed.

**`g1.py record`** collects a session in the Alpha window from the stores, read-only, so native
evidence stays separate from API evidence.

A follow-up found while preparing M1-R07: a stalled Core could hold a status request open
indefinitely. Requests now time out after 20 s, so the card shows "reconnecting". The Activity
list's stray indent is also gone.

Evidence: `docs/development/evidence/M1-R06.md`.

---

## First M1 packet (26 September 2026), superseded and kept as history

Date: 2026-09-26. Prepared by the coding agent for the founder's review. F01–F08 are
implemented. Work stops here until you give direction.

## What to review

- **Platform code:** frozen for G1 at **f7dada652a13b96cf04b167aae8cd7acb25d7d7d**.
- **G1 driver:** at 4b2c77a. It differs from the freeze only in `evals/g1_screen.mjs`.
- **Frozen checkout and build:** `/Users/kenil/Desktop/dev/alpha/alpha-g1`. It has its own
  `.alpha-runtime` and its own `Alpha.app`.
- **G1 data:** the three generated Apps with the data entered during G1, in
  `/Users/kenil/Desktop/dev/alpha/g1-run/data`.

Your own Alpha (the main checkout and its usual data) is separate and was not changed.

## Launch the demo

Open Terminal and run:

```bash
ALPHA_DATA_DIR=/Users/kenil/Desktop/dev/alpha/g1-run/data /Users/kenil/Desktop/dev/alpha/alpha-g1/apps/desktop/src-tauri/target/debug/bundle/macos/Alpha.app/Contents/MacOS/alpha-desktop
```

Launch it from Terminal as above rather than with `open`. Your usual Alpha has the same bundle
id, so `open` may bring that one forward instead. The header should say "Runtime connected".
Closing the window keeps Alpha running. Quit it from the Alpha menu, which also stops its Core cleanly.

Try it in this order:
1. **My workflows → Daily Food Log.**
   - Its own screen should open inside the window. **I could not confirm this step myself in
     the native window;** see "Not verified" below. Please check it first.
   - Log something ("2 idli and sambar", "1 plate"). The calories are estimated and marked
     "(estimate)".
   - Try Earlier day and Last 30 days.
2. **Job Opening Tracker.** Add an opening, press Open on it, log a step and change its stage.
   The stage filter counts update.
3. **Fits In Today Planner.** This App has no screen of its own: Alpha shows a form per action.
   Run "Fit my list into today's hours" with a few lines such as `Email Ravi 20m` and
   `Tax forms 2h`, and a number of hours.
4. **Assistant → a new request of your own.** This uses your Claude subscription. Expect 1–5
   minutes of questions and planning, and 5–13 minutes of building and checking. The card shows
   the stages. When it is ready, it offers "Open …" with a labelled sample-data preview.

To rebuild the same demo from scratch:

```bash
cd /Users/kenil/Desktop/dev/alpha/alpha-platform && git worktree add --detach ../alpha-g1-fresh f7dada6
```

```bash
cd ../alpha-g1-fresh && pnpm install --frozen-lockfile && just bundle-core && (cd apps/desktop && pnpm tauri build --debug)
```

## G1 outcomes (all through live generation, no source edits)

| | Calorie tracker | Collection/review | Held-out (chosen after freeze), no custom screen |
|---|---|---|---|
| Request | "Track what I eat and how much, with calories, history and trends" | "Keep a list of job openings I find and what I did about each" | "When I paste my to-do list with rough times for each item, fit it into the hours I say I have today, most important first, and tell me what won't fit. I'd just run it from Alpha whenever I need it; it doesn't need its own screen." |
| Clarification | 2 questions; defaults used | 2 questions; defaults used | 3 questions; defaults used |
| Result | Daily Food Log: entry with estimates, today by meal, correct entries, history, 7/30-day trends | Job Opening Tracker: openings, dated step log, stages with filtered counts | Fits In Today Planner: `read_list`, `fit_plan`, `report_plan` |
| Build | 1 attempt, 52 of 52 checks | 2 attempts: the screen failed type-checking, then was repaired; 49 of 49 | 1 attempt, 16 of 16 |
| Request → ready | 15.0 min (2.0 talking, 13.0 building and checking) | 15.9 min (4.6 + 11.3) | 6.5 min (1.8 + 4.7) |
| Estimated cost (subscription, not charged per call) | $2.41 | $2.82 | $1.58 |
| Primary use | 3 meals through its screen; estimates labelled; total 1,060 kcal | 2 openings, 1 step, 1 stage change through its screen | Real list planned: 215 of 240 min, 2 items won't fit, 1 estimated time; blank list refused |
| Reopen | Same Version and data after restart; screen shows the entries | Same | Runs again after restart |

- **Shared profile.** All three Apps run on one installed profile (`pyprof-391f9ca6e9db5bc54576`).
  A calorie entry was cancelled mid-estimate while the tracker saved an opening at the same
  moment. Each had its own worker process and scratch directory. The cancelled run saved
  nothing; the other run was unaffected, and a failed entry did not disturb either App. See
  F08.C04.
- **Evidence:** docs/development/evidence/F08.C01–C04.md and
  docs/development/evidence/logs/G1-20260926/, which holds the prompts, questions, briefs,
  plans, every attempt with its generated source, reports, screenshots, usage, `share.json`,
  `reopen.json` and `summary.json`.
- **Control evidence (fake routes):** docs/development/evidence/logs/F08-integration-20260926T100918Z/,
  and the full integration suite (133 tests) passing at each freeze.

## Failures along the way (kept, fixed in platform code, G1 restarted each time)

1. **Planning refused by the CLI.** The planner's schema used a keyword the Claude CLI rejects.
   Now only standard keywords are sent, and a regression test guards it.
2. **The builder ran out of time.** It spent all 12 minutes on a large brief with nothing to
   check, and the build ended with 18 minutes unused. Now:
   - a timed-out attempt is continued within the same limits;
   - the builder is told its time;
   - the assistant keeps first versions small.
3. **Checks failed on a symbol.** The plan used `"*"` for "any value", and the matcher compared
   it literally. The run was stopped before a repair could game it. Plans now use an explicit
   `{"$any": true}`.

Records: `logs/G1-20260926/failed/`.

## Not verified, and issues found

- **Generated screens in the native window.** The host serves them at `alpha-ui://`, and that
  path compiles. I verified the same sealed screens headlessly, with the shell's bridge
  against the real Core. When I opened the frozen Alpha to look, both Alpha apps on the Mac
  were quit within a minute, and I stopped rather than retry without asking. If the screen does
  not appear, the rest of the demo still works: the workspace keeps the actions and saved data.
- **Time to value misses the target.** The plan targets a median under 5 minutes for small
  builds. G1 took 6.5–16 minutes from request to ready. The calorie build used 706 of its 720
  seconds, so richer Apps sit at the edge of the 12-minute attempt limit.
- **Refusals show a Python class name.** For example: "ValueError: Paste your to-do list…".
  The platform should present an App's refusal in plain words.
- **Required fields don't block empty submissions.** The kit lets an empty form reach the App,
  which refused it.
- **The kit trend chart** draws oversized labels and bars when only one day has data.
- **Quitting during a build gives vague wording.** A creation cut off by quitting Alpha is
  correctly marked failed, with retry offered. Depending on timing, though, it says "The
  builder could not finish" rather than "Alpha restarted while this was being made".
- **The creation card's progress counters** add up across attempts, for example "54 checks" on a
  49-check candidate.
- **Only new Apps can be created.** Changing an existing App (a new Version replacing its
  release) has compare-and-swap underneath but no user flow until F10.
- **The builder route is internal.** It is the Claude Code CLI on your subscription, which
  suits development but is not a product entitlement (recorded 2026-09-25).

## Your call

G1's bar was three live requests through to use, one of them held out and one without a custom
dashboard, plus reuse of a shared profile. On my evidence it passed, with one caveat: the native
window step above is yours to confirm.

What should come next? The playbook suggests one of these:
- **Fix the issues above inside M1:** refusal wording, required fields, the chart, time to
  value.
- **Authorise M2 or later scope.** Record the instruction in
  docs/development/scope-authorization.md.
- **Change product direction** based on what you see in the demo.

Nothing beyond F08 has been started.
