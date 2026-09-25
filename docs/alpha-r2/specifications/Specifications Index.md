# Specifications index and authority

Clean-start R2 · handoff revision 3 · contract 0.2 · 25 September 2026.

## Owners

Current Release Specification owns normative fields, state machines and scheduling policy. Focused contract Markdown explains individual seams without defining alternative payloads. Implementation Blueprint section 10 owns shared-dependency mechanisms; the release specification owns their serialized fields.

Product Vision owns requirements; Current Release UX Specification owns journeys; System Architecture owns components; Implementation Blueprint owns code structure. Prototype_Scope_and_Acceptance owns scope, milestones and gates. TASKS.json owns ordered ticket steps and numbered checks; Task_Packets.md is its verified rendering. If an owner and a dependent summary disagree, correct the summary before coding the affected behavior; do not silently choose a convenient interpretation.

In an implementation checkout, docs/development/task_state.json plus its evidence is authoritative for actual progress. Delivery Checklist is the planning project's reconciled status view and starts pending; an external agent does not need live access to it. The playbook owns state/evidence rules. The initial execution scope ends at the M1 review even when later dependencies are satisfied.

## Machine contracts created during implementation

Generate from packages/contracts as consumed: brief/build/result (F02/F04), run/envelope/event (F01/F12), App/action/record/artifact/profile manifest (F05/F07), UI bridge (F03/F06), release/config/migration (F08/F10), capability/effect/approval/receipt (F13–F15), and trigger/occurrence (F17). Freeze schemas with positive and meaningful negative fixtures at the ticket that first uses them. Do not implement every future schema ahead of live generation.

The coding bundle contains only this active design. No previous code, migration or schema file is required. In the wider planning project, existing 0.1 JSON schemas, examples, fixtures, old proof archives and research are historical; they are excluded from the bundle and cannot establish conformance. Contract checks do not replace real generated behavior, native boundaries, UX or external-effect evidence.
