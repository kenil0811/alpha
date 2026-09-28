# Proposal: discovery-first creation, a Workspace Graph with Intelligence, and a shippable model route

Status: proposal for tech-lead review. Nothing in Parts A, B or D is built. Part C's monitor is on
branch `feat/avatar-model-monitor`.
Date: 27 September 2026
Author: Vikas (with Claude)

## Decisions requested

1. **A:** Replace the fixed "≤3 questions, then brief" turn with a risk-scaled discovery stage: ask about purpose and sources, research, then offer 2–3 options.
2. **B:** Add a Core-owned Workspace Graph that modules feed through declared mappings. They read from it only through a new scoped capability, which keeps "no App reads another App's records". On top of it, an Intelligence surface.
3. **C:** Add an Anthropic API route with the key in the Keychain next to the Claude Code CLI route, so Alpha can run for testers who don't have Claude Code.
4. **D:** Order of work. Taint labels on web and browser content (D1) must ship before cross-module graph reads (B, phase 2).

---

## A. Discovery-first creation

### Evidence (27–28 September; the same request, "a module for academics")

| | Bridge in-app chat (4–8 Sep) | Alpha (28 Sep) |
|---|---|---|
| First move | Offered 3 options: install the existing Academics module, customize it, or design new | 2 questions (grading scale, scope) |
| Role asked? | Yes. The user answered "professor", which changed the design entirely: Courses, Students, Office Hours | **No.** It assumed a student tracker (unstated assumption #1 of 16) |
| Sources asked? | Yes. Canvas was reported honestly as a gap | No. "Entry is manual" was assumed |
| Research | None in-app. The developer-session build (12 Aug) did OSS research through subagents | None before the brief. The builder may use WebSearch later |
| Options | Lettered text options, one question per turn. **This style came from the globally installed `superpowers:brainstorming` skill, not Bridge's own prompt** | None. One brief with "Assumptions you can change" |
| Outcome | Module failed registration once, got stuck at `promoted`, and is now absent | Brief ready; not built yet |

**Reading, without bias toward either side:**
- Bridge's *discovery* was better: it asked who the module is for and what it connects to. Its *delivery* was worse.
- Alpha's delivery pipeline is stronger (checked, reversible, fast). Its prompt deliberately trades discovery for speed:
  - "Ask at most three short questions…"
  - "choose reversible defaults… list them as assumptions"
  - "The first version is complete… Ask nothing about these"
- That trade is right for specific requests (the diet manager brief) and wrong for vague ones. For a vague request, the unasked assumption (student vs professor) is not reversible cheaply: it determines every collection.

### Design

A new **Discovery** stage replaces the single assistant turn when the request is under-specified.

1. **Gap scoring** (one structured call, about 6 s, like change triage). It rates the request on five decisive dimensions:
   - who it's for / their role
   - the outcome they want
   - data sources and integrations
   - cadence and automation
   - output or sharing

   Each dimension is marked *stated*, *inferable* or *unknown*, and each unknown gets an impact rating (high or low). A specific request with no high-impact unknowns skips straight to today's brief path.
2. **Ask** only about the high-impact unknowns, in one message with at most 4 questions, each with choices plus "something else".
   - Allowed topics: role/purpose, outcome, sources, cadence.
   - Still never asked: schema, layout, names, sort order. These stay as defaults.
3. **Research** (bounded to about 60 s, running in parallel with the user's answers where possible):
   - Existing modules in this Workspace, and graph entities once Part B exists.
   - Web search for how people in that role do this job, and which tools and sources they use (e.g., Canvas, Google Scholar).
   - Whether each named source is reachable with Alpha's capabilities (http / browser / not available). This gives an honest gap statement instead of a silent "manual entry".
4. **Propose** 2–3 options as structured cards, each with:
   - what it tracks
   - what it does automatically
   - what it can't do yet
   - rough build time

   One option is recommended, with a one-line reason. Options must differ in *scope or approach*, not cosmetics.
5. **Brief** from the chosen option. Assumptions keep their source, and a **fix is needed**: `_next_brief` currently marks new assumptions as `user_answer` whenever the turn carries answers.
6. **Create:** today's pipeline, unchanged.

**Contract changes:** `TurnOutput` gains a `discovery` object (gaps, questions, research notes with source URLs, options[]), and `BriefCard` gains `chosen_option_id`. The UI adds an `OptionsCard` component.

**Model and tools:** Discovery runs on the assistant route with `WebSearch`/`WebFetch` allowed, under a bounded turn budget. The assistant call is `--tools ""` today; that changes for this stage only.

**How to test this without fooling ourselves:**
- Build 12 fixture requests: 6 vague ("academics", "job hunt", "my finances"…) and 6 specific.
- For each vague one, an oracle lists the high-impact dimensions a good product person would ask about.
- Metrics:
  - high-impact dimensions asked vs assumed
  - user edits within the first 3 uses
  - time from request to a usable module
- Target: vague requests ask about at least 80% of high-impact dimensions; specific requests add no more than 15 s.

---

## B. Workspace Graph and Intelligence

### Why it doesn't break Alpha's isolation

Modules keep private record stores. The graph holds *shared identities and facts*, not other modules' records. A module writes to the graph only by projecting its own records through mappings declared in `app.yaml`. It reads only through a new `graph` capability, scoped to what the person granted.

### Data model (new `graph.sqlite`, Core-owned, local)

```text
entity(entity_id, kind, display_name, attributes_json, created_at, updated_at)
  kind ∈ person | organization | place | topic | document | event | course | …   (open set, registered)
entity_key(entity_id, key_kind, key_value)          -- email, url, domain, external id; unique per kind
mention(app_id, collection, record_id, entity_id, role, field, source_trust, observed_at)
relation(relation_id, from_entity, to_entity, type, attributes_json, valid_from, valid_to,
         confidence, provenance_json, evidence_refs_json)   -- one row = one meaning (Bridge rule)
claim(claim_id, entity_id, statement_json, status ∈ proposed|accepted|rejected,
      source_trust, evidence_refs_json)                   -- memory: suggested, then accepted
duplicate_signal(a, b, score, reason, status)       -- never auto-merge ambiguous identities
```

### How the graph fills

1. **Declared projection (deterministic, no LLM):**
   - `collections[].entities` maps fields to entity kinds and keys, e.g. `instructor → person(name)`, `email → person.key(email)`, `course → course(code)`.
   - Core projects on every record write, inside the same run.
   - The builder prompt and `APP_CONTRACT.md` gain the mapping section. The verifier checks that mappings bind to real fields.
2. **Suggested extraction (phase 3):** a background model pass over text fields proposes claims and relations as `proposed`. The person accepts or rejects them in Intelligence. Nothing is promoted silently.
3. **Identity resolution:**
   - An exact key match links automatically.
   - A name-only match files a `duplicate_signal` for review.

   This rule is carried over from Bridge.

### Access

**New capability family `graph`:**
- `graph.entities(kind, where)`
- `graph.neighbours(entity_id)`
- `graph.mentions(entity_id)`

Reads return entities and relations only, plus mention stubs (app name, record title), never another module's record body. The default scope is entities this module itself mentions. Wider scopes (per entity kind, or per source module) are per-module grants the person switches on in module Settings, like browser site grants.

**Assistant:** reads the whole graph (trusted Core) during Discovery research. For example, "you already track 3 courses in Teaching Planner; link this to them?"

### Intelligence surface (a shell rail item, matching Bridge's Intelligence)

- **Graph:** a force layout of entities and relations, filterable by kind or module. Every node opens its entity page; every mention opens the source module's record detail. Nothing is decorative (Bridge rule).
- **Entities:** a table per kind with a detail page showing the modules that mention it, relations, claims, and a merge/split queue from `duplicate_signal`.
- **Memory:** proposed and accepted claims with accept, correct and forget. There is a cap on how many suggestions are shown.
- **Per-module Intelligence section** on each module page:
  - what it knows (its mentioned entities)
  - its automations (schedules)
  - its capabilities and grants
  - its model usage

  This mirrors Bridge's Intelligence and Governance sections, sitting below the module's view.

### Taint (a prerequisite for cross-module reads)

`http`/`browser` content enters module model calls today with no label. Before any graph data crosses modules:
- Anything projected or extracted from web or browser-sourced records carries `source_trust = external`.
- External-trust claims can't become `accepted` without a human.
- Module model calls wrap external content as data (not instructions) and record the label on `model_calls`.

This follows Bridge's model: labels stay attached and are only removed by a rule or a human.

### Phases

| Phase | Scope | Size |
|---|---|---|
| G1 | graph.sqlite, declared projection, Entities + Graph views (read-only), backfill projection on activation | M |
| G2 | `graph` capability + per-module grants, assistant retrieval in Discovery | M |
| G3 | Suggested extraction, claims/Memory with accept/reject, duplicate review | L |
| G4 | Per-module Intelligence section, graph-aware quick filters | S |

Sizes are relative (S < M < L); no dates without a spike.

---

## C. Model routes

- **Built on the branch:** a connection monitor under Settings → Models.
  - CLI found, version, signed in, last success/failure
  - Check now, Sign in
  - plain-language fixes
  - failures surfaced in the assistant panel and on the Avatar

  This addresses the silent failures on 27 September: a CLI too old for `--permission-prompts`, then a signed-out CLI.
- **Proposed:** an `anthropic-api` route.
  - The key is kept in the Keychain; Core never logs it and generated code never sees it.
  - Per-stage model choice as today.
  - Real metered cost shown in Activity. Today the cost basis is "subscription_unmetered".
  - This is required before anyone without Claude Code can test Alpha.
  - Bridge already has BYOK in a Local-only vault (ADR-181); port the pattern, not the code.

## D. Other prerequisites found in review

0. **Planner timeout discards a finished module** (seen twice on 28 Sep, "job search" request).
   - The builder finished in about 4 min and passed every structural check (12/12 handlers bound).
   - The parallel planner call hit the 300 s limit in `StructuredInference` both times.
   - `CreationService` then failed the creation with `plan_unavailable` and cancelled the build with reason `cancelled_by_user`, which is a mislabel.
   - Fix:
     - On planner timeout, keep the candidate and verify it against the preliminary plan from the brief's examples.
     - Retry the planner once in the background with a longer limit.
     - Label the cancellation as a platform reason.
1. Taint labels for `http`/`browser` content (see B). **Blocks G2.**
2. Generated Python runs as the user with network and disk reachable (no rlimits, no sandbox). F20 is still open, and this should be decided before external testers.
3. `external_write` actions have no approval gate. The catalog promises one; either build it or refuse `external_write` actions until it exists.
4. The declarative `screen` has no render check (only `ui.entry` does).
5. Every integration test uses the fake route, and there's no CI. Add one nightly live-route smoke test on the 12 Discovery fixtures.

## Open questions for the tech lead

1. Should the graph be one SQLite file or tables inside `control.sqlite`? One file is proposed, for export, deletion and backup clarity.
2. Is the entity kind set platform-registered or module-declared? The proposal: platform core kinds, plus module-declared kinds namespaced by app.
3. Should Discovery research run on Sonnet with WebSearch, or through a separate research worker with its own budget?
4. Should the "Use these defaults" escape hatch stay? Proposed: yes, but high-impact unknowns stay flagged on the brief card.
