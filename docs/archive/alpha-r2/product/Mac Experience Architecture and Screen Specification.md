# Mac experience and screen ownership

Baseline R2 · 24 September 2026. The Current Release UX Specification owns behavior; this file maps surfaces to trusted ownership. Older wireframe PDFs illustrate prior ideas and do not override R2.

| Surface | Owner | Content and actions |
|---|---|---|
| Assistant | Trusted shell | Request/context, clarification, progress, result and change/repair conversation |
| My workflows | Trusted shell | User-created reusable work, enabled/paused/attention state and open/run/settings |
| Workflow workspace | Shell frame plus isolated generated UI when present | Primary work surface, with trusted access to Activity, settings and versions |
| Activity | Trusted shell | Tasks and App runs, results, waiting states, receipts and recovery |
| Connections | Trusted shell | Account metadata, login/reconnect, scope and revocation; never raw secrets |
| Action review | Trusted shell | Bound account/destination/payload and explicit decision; cannot be generated content |
| Change review | Trusted shell | Candidate behavior, data/permission changes, validation and activation/rollback |
| Runtime/tray | Native host with shell status | Runtime availability, open window, pause where appropriate and explicit quit |
| Settings | Trusted shell | Model routes/budgets, storage/disclosures, export/backup and diagnostics |

Keep primary navigation small. One-off outputs remain in conversation/Activity rather than becoming permanent workflow tiles. A reusable workflow without custom UI uses a shell-provided status/settings/history view. Trusted approval and login chrome must remain visibly outside generated content.

Native responsibilities are window/tray lifecycle, managed process profiles, secure credential adapter, selected-file grants and update integration. Business rules remain in Core/generated packages. A web preview can establish UI behavior but cannot establish native close/quit, Keychain, sandbox or packaged-startup behavior; those require Mac evidence.
