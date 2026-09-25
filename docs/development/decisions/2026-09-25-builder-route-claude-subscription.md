# Decision: F02 builder route uses the founder's Claude subscription via the Claude Code CLI

Date: 2026-09-25. Source: founder instruction in the Claude Code session, verbatim:

> so i dont want to use key. I want you to for now, set up the harness such that it uses my
> claude subscription (maybe in a terminal with claude code cli for now)

## What changes

- The Builder Harness Interface names OpenCode headless as the first adapter candidate and the
  Claude Agent SDK as fallback, both driven by a BYOK provider key through the platform model
  gateway. For the initial engagement the first qualified adapter is instead a **Claude Code CLI
  adapter** (`claude -p`, headless, stream-json events) authenticated by the founder's own Claude
  subscription login on this Mac. No provider API key exists in the platform.
- The adapter still implements the same seam (`start/events/cancel/result/capabilities`), private
  per-build configuration and workspace, host-enforced process-tree cancellation, normalized
  events and retained attempts. Usage is recorded from the CLI's result message; monetary cost
  is reported as "subscription (not metered per call)" rather than fabricated.

## Consequences and limits (stated, not hidden)

- Current Architecture Decisions records that a consumer subscription is not assumed to be an
  embeddable product entitlement. This route is therefore an **internal development route on the
  founder's machine only**; it cannot ship to other users. F22's "second BYOK provider" and any
  distribution decision must revisit this.
- The platform cannot inject credentials into this route (the CLI owns its login), so the
  "scoped gateway credential" for builders is replaced by: private config directory, explicit
  tool/permission allowlist, workspace-confined cwd, and no ambient project settings. Recorded
  as an F02 limitation for F20 to qualify.
- Runtime model calls (F05 `ctx.models`) need a route too; until a key exists they will use the
  same CLI in non-agentic mode with a bounded prompt and validated structured output, with the
  same usage/cost caveat.

## Bookkeeping

Snapshot files are unchanged (immutable). The affected packet is F02; its checks are unchanged
in meaning: a real authorized model invocation producing source that compiles and returns
independently checked outputs (F02.C01), failure classification, cancellation with descendants,
private config and retained usage.
