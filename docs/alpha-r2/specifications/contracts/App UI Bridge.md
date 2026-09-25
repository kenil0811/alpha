# Generated UI bridge

Baseline R2 · contract 0.2. Owns the narrow unprivileged presentation protocol. Generate the typed definitions during F03/F06.

Every message has `protocol_version`, `session_id`, `request_id`, `type` and a schema-validated payload. Bind the session to exact window, App/release, allowed read projections/actions and expiry. Core/parent derives these claims; the child cannot broaden them. Use a transferred MessagePort established with the intended frame; revalidate and revoke on navigation/release change. Opaque origin strings alone are not identities.

| Request | Permitted behavior |
|---|---|
| `records.query` | Read a declared bounded view/projection |
| `action.invoke` | Invoke a declared action with validated arguments; return operation/run ID |
| `operation.observe` | Follow authorized run state/events with a cursor |
| `artifact.open` | Ask the trusted shell to preview/export a scoped artifact |
| `input.select` | Ask the shell for scoped file/input selection; no arbitrary path strings |
| `shell.navigate` | Request a named trusted destination such as run details/settings |

Results carry request ID and either typed data/operation ID or typed error/recovery metadata. All mutation goes through actions. Client optimistic updates must reconcile with committed revisions and show failure; never silently mark a failed save as stored.

No bridge method exposes secrets, raw SQL, arbitrary HTTP, native IPC, shell commands or another App. Generated UI cannot render a trusted permission decision, submit grants or invoke an approval endpoint. CSP and frame sandbox deny ambient network/navigation/forms/popups/downloads; the native implementation is qualified in F03/F20. Accessibility and visual quality still apply inside the boundary.
