# Current release UX specification

Baseline R2 · 24 September 2026. Owns user journeys and interaction quality for the Mac private alpha. Prototype screenshots and older wireframes are reference material, not substitutes for these behaviors.

## 1. The user's mental model

“Tell Alpha what you want done. Use what it makes. Ask it to change or fix it.” Users do not need to understand Tasks, releases or SDKs. Use familiar surface labels: Assistant, My workflows, Activity and Connections. Open a workflow into its useful working surface; keep configuration/history accessible without crowding the main task.

The assistant is the front door, but chat is not the only ongoing interaction. Repeated structured input and review need direct controls. A background workflow may only need settings, status, latest result and history. A one-off Task ends in its result card/file and remains findable in Activity, without cluttering My workflows.

## 2. First use

Explain local runtime availability and remote model processing in plain language. Connect one supported BYOK provider through trusted settings. Report unsupported/missing model access precisely; do not expose raw secrets in a chat prompt. Offer a simple goal input with a few illustrative prompts, not a compulsory template choice. Defer site login, file selection and additional permissions until the request needs them.

Installing, connecting a provider and creating a first result must not require terminal commands or package management. Until F22 proves this, label the product an internal development build.

## 3. Request and clarification

Show the user's request, selected context chips and a concise interpretation: desired outcome, main input/source, useful result and important assumptions. Ask one to three short questions together when genuinely independent. Offer choices plus free text where helpful. Do not ask the user to choose SQL schemas, components or technologies.

Ask if the answer changes source eligibility, what counts as a useful result, a required personal fact, storage/external action scope or important recurring behavior. Choose reversible defaults for layout, names and sorting; disclose assumptions without turning setup into a requirements questionnaire. Permit “use this for now” and revision later.

When a request exceeds a capability, explain the missing piece and a useful partial outcome. “I can prepare the text; audio generation is not connected” is honest. Presenting a text file as a podcast is not.

## 4. Creating a result

Progress stages describe user value: understanding, building, checking, ready, or needs your input. Detail can expose tests and logs for diagnosis. Do not stream irrelevant shell commands into the main flow. Show cancellation and whether cancelling affects anything already completed.

The user may inspect a preview while checks run, with a visible Preview label. Example data stays labeled and separate from personal data. The final card says what works, how to start, what access is still needed and any material limit. A failed build presents a specific next step: answer, retry within budget, revise scope or keep the current version.

For a local tool with no expanded permissions, the initial request can authorize building and trying a reversible candidate. Activation must still check compatibility and required grants; avoid a redundant consent screen purely because a technical release record exists. External side effects require the appropriate trusted action review.

## 5. Reusable components and generated compositions

| Pattern | Use when | Required behavior |
|---|---|---|
| Quick entry | Frequent small additions | Sensible focus, keyboard submit, parsed preview when ambiguous, immediate saved/error state, edit/undo where supported |
| List/table | Compare, filter or review many records | Visible key fields, sorting/filtering, pagination, selection and drill-down; no unreadable column dump |
| Detail drawer/page | Inspect one item and act | Source/provenance, editable user fields, clear actions and outcome feedback |
| Review queue | Decide on incoming items | Next/previous, status, bulk actions only when safe, preserved decisions and reason/context |
| Metrics/trend | Understand aggregate change | Date range, units, empty/missing data distinction, consistent totals and useful chart labels |
| Form/action review | Supply inputs or confirm an effect | Validation, selected account/destination, exact fields/files, consequences and current status |
| Artifact result | A file/report is the output | Preview, filename/type, provenance, save/export/open and retry if delivery failed |
| Background workflow card | Ongoing work needs little custom UI | Enabled/paused, last and next run, latest output, attention needed, settings and history |

Use generated React with shared tokens and components. The builder can write custom interaction code when existing components do not fit. Automatic argument-to-form rendering is a fallback for rare/admin actions, not the expected primary experience for a tracker or review workflow.

The kit supplies typography scale, spacing, semantic color, focus states, radii, elevation and chart colors. Use a restrained default palette. Primary actions are visually clear; status does not rely on color alone. Keep implementation terms out of everyday surfaces unless they help a real decision.

## 6. Example quality bars, not prebuilt product screens

**Calorie request:** the primary interaction is adding food/portion quickly. Show parsed or estimated values with an easy correction path, today's total, editable history and a trend. Empty states explain how to start. Estimates are labeled; missing dates are not shown as known zero. Do not ask users to type every derived field into a generic database form.

**Job request:** orient around fresh opportunities to review and application progress. Show useful role/source/match details and an actionable next step. Preserve applied/declined/user notes on refresh. “Help apply” opens the supported browser/action flow with actual supplied facts and missing information highlighted. A few search boxes cannot satisfy this journey.

**Background request:** expose status, settings and results. Do not invent a dashboard just to fill a screen. **One-off request:** deliver the artifact or action result and stop unless the user asks to make it repeatable.

These views must be produced by the user creation path. Handwritten reference compositions inform quality; they cannot count as generated output in evaluation.

## 7. Browser and action assistance

Trusted shell surfaces own account connection, login takeover, permission and consequential review. Display what site/account is in use. Let the user take over for login, MFA, CAPTCHA or unsupported interaction and resume when appropriate.

Before an external submission, show the destination, acting account, exact content/field summary, attachments, unresolved facts and expected effect. Recheck after edits. Filling a form is not submission, and some fields can autosave; communicate the actual qualified site's behavior. Keep prepared, filled, submitted, failed and unknown states distinct. Do not mark an application submitted without a receipt or equivalent evidence.

An existing bounded authorization should carry through ordinary steps. Ask again when account, recipient, payload, operation scope or other material terms change. Ordinary clarification is not action approval.

## 8. Operation, changes and repair

Activity answers: what ran, when, why, what changed, where is the result and what needs me? Each item has human-readable state, provenance and useful recovery. Expand for technical evidence. Waiting on user input, expired connection, rate limit and uncertain external outcome need distinct messages and next actions.

“Change this” reuses the current goal and context. For simple settings, show and apply the requested values. For code/schema changes, preview behavior and data impact while the current release remains usable. If the candidate fails, say so and retain the current version. Changes in access require clear review. Data restore is a separate destructive choice from reverting code.

“Fix this” should propose a diagnosis grounded in the failing run, then verify a candidate. A reconnection problem should open reconnect, not rebuild the whole App. An uncertain action should open reconciliation, not retry blindly. The user can pause a workflow while investigating.

## 9. Local availability

Say “Runs while Alpha is running on this Mac.” Closing the window leaves the tray/runtime active; quitting stops it. Sleeping/offline operation has explicit limits. Show last run, next run and missed occurrences. On relaunch offer manual retrigger; never silently catch up. Always-available/cloud execution remains unavailable until implemented and explicitly configured.

## 10. Required UX validation

For each generated UI inspect empty, populated, loading, saving, validation error, provider failure and narrow-window states. Exercise primary input, correction, filtering/detail and result/action feedback. Initial widths: 768, 1024 and 1440 CSS pixels, adjusted if the native minimum width is higher; record what was actually tested. Verify keyboard focus, readable contrast, labels and screen-reader names. Automated accessibility checks supplement human inspection.

Functional checks validate saved data and actual outcomes behind the interface. Visual review assesses hierarchy, density and clarity. Neither substitutes for the other. G1 checks generated quality early; F23 tests whether nontechnical users can complete real journeys without coaching. Keep failures and intervention notes.
