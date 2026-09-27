# Product vision and requirements

Baseline R2 · 24 September 2026. This file owns product intent and requirements. Release sequencing belongs to the implementation plan. These are design requirements, not implementation claims.

## What Alpha is for

Alpha is an agentic platform for the work around people's work. A nontechnical user describes an outcome; Alpha helps specify it, assembles the necessary behavior and presentation, tests it, delivers it and keeps it useful. It can connect existing tools, process information, maintain user-owned data, act on approved systems and produce useful outputs.

An app is one possible output. A document, one-off action, recurring workflow or background monitor may be a better answer. The user should not have to select a software architecture before asking for help. Alpha is not limited to personal trackers, and its value is not measured by how many screens it generates.

The founder/platform team builds the assistant, creation system, runtime, capabilities, data services, UI kit and recovery mechanisms. Users supply goals, access, preferences and decisions. AI produces workflow-specific logic, data definitions, mappings and optional interfaces. Reusable recipes can accelerate creation but must not define a closed catalogue.

## Who the first release serves

Individuals with recurring information or administrative work, a Mac, and willingness to participate in setup and review. They need useful personal automation, not production-scale hosting or enterprise guarantees. Initial qualification uses trackers, opportunity review/application assistance, information monitoring and file transformation because together they exercise different parts of the same platform.

The initial audience is deliberately narrower than the eventual vision. WhatsApp order handling, invoices, inventory, portal-to-podcast workflows and résumé assistance remain valid future outcomes; they require qualified capabilities and account access that the first release may not provide. Do not market those illustrative examples as shipped integrations.

## Requirements and traceability

| ID | Requirement | Acceptance / implementation |
|---|---|---|
| R01 | Start from ordinary language, ask material questions and retain the understood goal | A01–A06; F04/F08 |
| R02 | Choose answer, Task, artifact or reusable work; UI is optional | A03/A04; F04/F11 |
| R03 | End users create workflow-specific behavior without platform changes | A06/G4; F02/F07/F19 |
| R04 | Generated interfaces have clear primary actions, fast input, readable views and correction paths | A01/A02; F06/F07/F23 |
| R05 | Store user-owned records and artifacts with validation, provenance and export | A01/A04; F05/F09/F21 |
| R06 | Connect qualified HTTP, browser and file capabilities with understandable access | A02/A03; F13/F14 |
| R07 | Assist supported applications/forms, distinguish draft/fill/submit and retain outcomes | A02/A04; F15/F16 |
| R08 | Run reusable work manually or on local schedules; show missed work without automatic catch-up | A03; F17 |
| R09 | Make decisions at runtime using bounded model calls when deterministic rules are insufficient | A01/A02; F05/F18 |
| R10 | Change and repair behavior through conversation while preserving data and working versions | A05; F10/F18 |
| R11 | Share actions across assistant, generated UI and triggers; enforce policy in the platform | F05/F07/F15 |
| R12 | Persist execution state, evidence and meaningful failures; cancel and recover honestly | A05; F12/F15 |
| R13 | Keep local persistence distinct from remote inference; protect secrets and selected context | F02/F20/F21 |
| R14 | Generated code/UI cannot inherit native, account or cross-App authority | F03/F20 |
| R15 | Bound build/runtime time, attempts, data and model spending | F02/F07/F15/F19 |
| R16 | Install and use a Mac product without a terminal; window close preserves runtime and quit stops it | F01/F17/F22 |
| R17 | Design portable packages/providers for later Windows and eligible cloud execution | Architecture; future roadmap gates |
| R18 | Evaluate real generated outcomes, held-out requests and nontechnical independence | G1/G4/G5; F19/F23/F24 |
| R19 | Maintain shared services, SDK/UI components and dependencies centrally while keeping each solution's data, authority and execution separate; upgrade through verified versions | F05–F08/F10/F20/F22 |

## Principles that resolve product choices

**Deliver useful work.** Ask whether the user can complete the primary journey, not whether a package compiled. Never show success for work that did not happen.

**Clarify consequential ambiguity.** Ask about goals, source coverage, uncertain facts or actions when the answer matters. Choose reversible layout defaults without making the user a designer. Do not treat brevity of setup as more important than correctness.

**Make data dependable.** Code is replaceable; user corrections and decisions are not. Refreshes, repairs and rollbacks must preserve them or clearly preview an explicit migration/restore.

**Use structure where it helps.** Tables often support the data layer, review and tracking. Quick entry, charts, detail views, files and background work may be the best interface. A generic CRUD screen is a fallback, not the universal quality target.

**Use existing tools.** Prefer qualified APIs for stable structured work; use browser interaction where necessary and permitted. Keep authenticated state with providers. Alpha connects to a user's systems rather than requiring them to move everything inside Alpha.

**Make imperfect operation recoverable.** Show access failures, missed schedules and unsupported sites. Keep evidence, context and working versions so AI-assisted repair is practical. “Occasionally breaks” cannot excuse silent loss or duplicate actions.

**Expand capabilities, not domain branches.** A new supported workflow should usually need only a new generated package. A genuinely new device/service capability may require a platform extension with shared semantics and tests.

**Share maintained building blocks.** Shared services and versioned packages are the normal foundation for generated work. Users must not manage Python environments or repair copied platform internals app by app. Shared code does not grant shared data access. Exact versions and tested candidate upgrades keep common fixes manageable without changing a working app underneath it.

## Longer-term product direction

Eligible always-available workflows, Windows, deeper account integrations, explicit memory/context, voice/screen input and governed desktop actions extend the same model. Avoid continuous monitoring, unbounded autonomy or ambient cross-workflow memory as defaults. Cloud deployment must explicitly change data/execution location; it must not be hidden inside a repair or builder choice.
