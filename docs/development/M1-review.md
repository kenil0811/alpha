# M1 review: the working G1 creation experience

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
