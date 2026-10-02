# Alpha bugs

Bugs found in Alpha, with their status. Newest group first. Alpha's runtime keeps its own list of
the failures it detects (`<data dir>/bugs.md`, written by `services/core/alpha/bugs.py`); this file
is the one people and coding agents keep.

Status: **open**, **fixed** (verified), **deferred** (with the reason).

## 2026-10-01: creation flow review (screenshots of a new project and the chat)

### Chief of Staff panel

| # | Bug | Status |
|---|---|---|
| 1 | Title "Chief of Staff" wraps to two lines in the header and the top line is cut off. | fixed (tests) |
| 2 | The subtitle ("Untitled proje…") is truncated and sits under the panda avatar. | fixed (tests) |
| 3 | The header is see-through: the subtitle "Home" is drawn over a scrolled message. | fixed (tests) |
| 4 | The composer placeholder "Ask Chief of Staff" wraps and its second line is cut off. | fixed (tests) |
| 5 | A half-visible icon sits below the composer, bottom right. | fixed (tests) |
| 6 | "Questions and options are on the page." shows while Alpha is still thinking, in faint grey. | fixed (tests) |
| 7 | "ChatGPT couldn't answer." gives no reason. | fixed (tests) |

### Project page

| # | Bug | Status |
|---|---|---|
| 8 | The session row's Archive button sticks out past the card's right edge. | fixed (tests) |
| 9 | A "Click to edit" native tooltip covers content between Alpha's notes and Sub projects. | fixed (tests) |
| 10 | Visible helper sentence "Add a goal: what this project is for, in your words." | fixed (tests) |
| 11 | The project stays "Untitled project" with a folder icon after the person describes it. | fixed (verified live: "Notes App", notebook icon) |
| 12 | The creation card is a narrow box with a left rule, box in a box, no gap above Alpha's notes. | fixed (tests) |
| 13 | The waiting state says only "Thinking about your request… 0:45", not which step. | fixed (tests) |
| 14 | Uppercase labels ("NEW PROJECT", "HOW ALPHA UNDERSTOOD IT", "HOW YOU'LL USE IT"). | fixed (tests) |
| 15 | Sub projects says it's empty twice ("None filed here yet." and the empty box). | fixed (tests) |
| 16 | Alpha's notes and Sub projects use tall empty boxes on a new project. | fixed (tests) |
| 17 | "Add a sub project…" is a native select, larger than the buttons around it. | fixed (tests) |
| 18 | "New session" is filled green; primary buttons elsewhere use the app's main colour. | fixed (tests) |
| 19 | The page says Archive, the sidebar menu says Delete, for the same action. | fixed (tests) |
| 20 | The session title is cut off mid-second-line. | fixed (tests) |
| 21 | No way to rename a project or change its icon from the sidebar's right-click menu. | fixed (tests) |

### Creation card and AI text

| # | Bug | Status |
|---|---|---|
| 22 | "How Alpha understood it" overflows the narrow chat panel; the text is cut off at the right. | fixed (tests) |
| 23 | The page shows far more than the Q&A: understanding, a reply paragraph and the whole brief. | fixed (tests) |
| 24 | The plan is pasted into the card instead of being stored with the project as `plan.md`. | fixed (tests) |
| 25 | AI replies are too long (the reply restates the brief that follows it). | fixed (tests) |
| 26 | Too many font sizes: about 20 distinct sizes across the CSS. | fixed (only the five --text-* tokens remain in CSS) |
| 27 | A request made from Home still shows its questions in the chat, not on a page. | fixed (tests) |
| 28 | Older conversations say "module" and assume a student (before the discovery-first flow). | deferred: old data; new requests use the new flow |

### Builder

| # | Bug | Status |
|---|---|---|
| 29 | Quick Capture Notes was briefed but not built: the Claude Code CLI refused with "Your organization has disabled Claude subscription access for Claude Code" (builds `build_ba1d875f…` 07:02Z and `build_9a540f9a…` 07:08Z). The `claude` CLI on this Mac is signed in to a different account and organization ("Claude Edu", same email) than the Claude desktop app, which signs in its own Code sessions. | fixed: the real cause was #45; the CLI's own login is in an organization that refuses Claude Code (403 `oauth_not_allowed_for_organization`, reproduced), but builds no longer use it |
| 37 | ChatGPT was chosen in + → Advanced, but the choice covers one chat message only: the answers on the page, the options, the plan's checks and the build all ran on Claude. A request's model must carry through everything it starts. | fixed (verified live: chat turns run on chatgpt-codex-cli); a Codex build is not yet proven live |
| 38 | Settings → Models had no default saved (the star was never set), so every stage fell back to Claude without saying so. | fixed (verified live: saves now reach Core, see #41) |
| 39 | The + → Advanced model list marks nothing when no override is set; the provider actually in use (the Settings default) isn't highlighted. | fixed (tests) |
| 41 | "Load failed" when choosing a model: Core allowed only GET and POST from the app, so every PUT/DELETE (model, default star, keys, settings) was blocked by the browser. Root cause of #38. | fixed (verified live: preflight allows PUT, saves return 200) |
| 42 | Claude shows "connected" (green) in Settings → Models while its organization refuses every call. | fixed (tests): a refused call turns the row red with the reason until a call works or you reconnect |
| 43 | The per-provider model picker reads "Model" when nothing is saved, instead of saying the default is in use. | fixed: "Default model" |
| 45 | The builder ignored Alpha's own Claude sign-in (Settings → Models) and ran on the `claude` CLI's login, a different account and organization from the chat's. Chat calls worked; every build was refused. | fixed (verified: Alpha's sign-in runs the CLI with no error, and the builder process reads it from the Keychain; a full Claude build not yet run live) |
| 44 | Settings → Models has both a model picker on the Claude row and per-stage Claude pickers below it, writing the same setting. | fixed (tests): one Claude model on the Claude row (`models.claude_model`); the per-stage lists are gone, thinking settings stay |
| 40 | There's no way to pick a model within a provider (e.g. which ChatGPT or Claude model); only the provider. | fixed (verified live: Codex lists GPT-5.6 Sol/Terra/Luna and GPT-5.5) |
| 32 | That refusal isn't recognised as a sign-in failure (`harness_claude_cli.py` matches only "Not logged in"), so it's reported as a generic harness error. | fixed (tests) |
| 33 | The person is told to try again, which can't work; it should point to connecting another model (`creation.py` `_failure` has no `harness_auth` branch). | fixed (tests) |
| 34 | Checks run on the untouched template after the harness did nothing, so "has no action 'capture_note'" hides the real cause. | fixed (tests) |
| 35 | The planner, assistant and weekly review log empty error text for the same refusal. | fixed (tests) |
| 36 | No Claude API-key route is enabled, so "use an Anthropic API key" has nowhere to go. | deferred: the API model route proposal (d7ccb2e) |

### Tests and tooling

| # | Bug | Status |
|---|---|---|
| 30 | `rail.test.tsx` "makes the project only once" is flaky: it looks for the reply once with `getByText` before it renders. | fixed: waits with `findByText` |
| 31 | `layout-check.js` missed bugs 1, 3, 4 and 26: no textarea placeholders, no vertical cut, no covered text, no font count. | fixed: all four checks added |
