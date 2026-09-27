# Deployment and execution

Baseline R2 · 24 September 2026. This file owns execution placement and deployment boundaries.

## Local alpha

The Mac host supervises one Core process and registered builder, App, parser and browser workers. Closing the main window preserves the runtime/tray; explicit quit stops it. Core owns durable state; host owns process control. On unexpected exit, restart reconciles leases and incomplete operations instead of assuming success. Workers are leased and bounded; no permanent server per App.

App UI is compiled static content served through the isolated surface. App actions run on demand. Schedules dispatch through the same coordinator/action contract. Only one active run per trigger is allowed initially; missed/overlap states remain visible. Sleep/offline/quit cannot satisfy an always-on promise. No automatic catch-up after relaunch; manual retrigger makes a new linked run.

## Shared installations and isolated workers

Compatible App and Task workers read the same immutable managed dependency installation. Each lease has a separate process, private writable scratch and owner-bound broker credential. Static UI is built against pinned shared packages; generated data and secrets never live in a profile. Installation, pinning, upgrades and cleanup follow Implementation Blueprint section 10. A dependency profile describes executable bytes; an execution/sandbox profile describes allowed authority. Neither substitutes for the other.

Profile preparation is a trusted platform operation and cannot happen through a running App's package manager. Activation/run dispatch requires an installed, intact, supported profile and its exact compatibility record. Missing/corrupt profiles block affected execution with a repair path; never substitute the newest available profile. Core/browser services remain centrally maintained and enforce per-caller scope.

## Execution profiles

| Profile | Allowed inputs and access | Release condition |
|---|---|---|
| Internal synthetic | Nonsensitive fixtures, bounded workspace, no production accounts | F01/F02 operational checks; explicitly not hostile-code qualification |
| Builder | Copied context, toolchain, approved dependency/model routes, no production secrets/data | F20 filesystem/process/network qualification |
| App/Task worker | Immutable code, scoped SDK broker token, temporary files, no ambient network/home | F20 qualification plus current grant |
| Parser | Selected input handle, bounded output/CPU/memory, no network | Format-specific parsing tests and F20 profile |
| Browser provider | Dedicated account profile, approved navigation/actions and protected state | F14/F15 functional behavior plus F20/F21 protection |

Qualify actual native runtime dependencies, startup, cancellation, resource limits and updates. A Linux CI pass does not establish Mac host behavior. No Docker/local-VM requirement is imposed on users unless the native containment candidate fails and a deliberate replacement decision is made.

## Future always-available deployment

Create an explicit deployment target and migration flow for eligible Apps. Initial future shape: authenticated modular service, PostgreSQL, object storage, managed secrets/scheduling and ephemeral isolated workers. This is a direction, not a selected cloud vendor or a current implementation task. Introduce tenant identity, quotas, costs, retention and remote access before external cloud execution.

An App has one authoritative execution/data placement initially. Moving it requires snapshot/export, compatibility checks, secret reattachment, disabled old triggers, successful new activation and rollback planning. Do not introduce active-active sync as part of first cloud support. Device-dependent actions require an online scoped device bridge and visible availability; cloud does not gain access to a sleeping Mac.

## Windows

Share contracts/Core/SDK and portable generated logic. Separately qualify process trees, IPC, paths, credentials, selected-file access, containment, browser distribution and installer/update behavior. Run shared tests early where practical, but label Windows product support pending until native gates pass.
