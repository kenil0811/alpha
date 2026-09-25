# Builder harness interface

Baseline R2 · contract 0.2. Owns the adapter seam. BuildRequest/Result and build state are defined by Current Release Specification section 4.

The first adapter candidate is OpenCode headless. Claude Agent SDK is the fallback if the qualification ticket records a blocker. Previous DeepSeek-first and mandatory two-adapter benchmark requirements are retired. A deterministic fake may test lifecycle controls but never prove generation quality.

| Method | Required semantics |
|---|---|
| `start(request)` | Lease-bound attempt, private workspace/config, return adapter session reference |
| `events(session, cursor)` | Normalize progress/tool/usage/diagnostic events; preserve raw sanitized references where useful |
| `cancel(session)` | Request abort, then host-enforced process-tree termination within configured grace |
| `result(session)` | Candidate package reference/digest or explicit failed/cancelled result, with usage and diagnostics |
| `capabilities()` | Exact supported checkpoint/resume/cancel/usage features; no assumed parity |

The adapter cannot seal/activate a release, grant permissions, open production browser sessions or mutate live records. Builder receives selected context, SDK/kit docs, dependency profile, validation plan and budget. Core chooses the route and owns durable lifecycle; upstream final text never certifies success.

Qualification F02 covers actual generated execution, structured event translation, failure classification, budget reporting, private configuration, scoped gateway credentials, cancellation/descendants and restart cleanup. F03/F20 add native containment. Pin exact versions. Check licensing/redistribution in F22. Persist all failed attempts; do not cherry-pick candidate success.

There is no automatic mid-build harness switch with inherited credentials or opaque sessions. A fallback produces a new attempt from explicit sanitized inputs. Resume, if supported and qualified, must preserve exact workspace/package identity and current authority.
