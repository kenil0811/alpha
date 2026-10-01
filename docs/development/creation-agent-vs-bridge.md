# How Alpha makes a new project, compared with Bridge (1 October 2026)

**The baseline is Vikas's process (below).** Bridge practices are adopted only where they add
to it. Bridge sources: myzazoo branch `claude/builder-research-governance` (`src/prompt.md`,
`src/fetch.ts`, `modules/governance`), and the full Bridge platform in Relationship OS
(`platform/apps/api/src/builder/run.ts`). Relationship OS was read, not edited.

## The process (baseline)

1. **Understand.**
   - Role first.
   - Outcomes, optional. Each question offers options plus the person's own words; the outcomes
     question also offers "Not sure yet: show me what's possible", which sends research to find
     what is possible.
   - The software they use today.
   - Nothing is asked when the background already answers it; the assumption is shown instead.
2. **Research the domain.**
   - How their tools connect.
   - What people in that role do in each tool, and between tools.
   - Open-source projects.
   - Reddit and forum feedback on the problems people hit.
3. **Recommend and decide.**
   - A short, plain account of what was found.
   - Two or three things Alpha can make.
   - Only the decisions that change the final design.
   - Outcomes are asked here if they were left open.
4. **Build research.**
   - Open-source projects that already do the chosen thing.
   - APIs that do it or part of it.
   - A further question only if that research raises a real decision; otherwise build.
5. **Throughout.**
   - Assume the person is not technical unless they say otherwise.
   - Professional and brief; never childish, never padded.
   - High integrity.
6. **Screen.**
   - New project makes a blank project at once.
   - The page has "Describe your project" and Import.
   - The first message goes to the chat.
   - The questions, options and build show on the project's page; the chat only points to
     them.

## Where each step lives in Alpha

| Step | Alpha (now) |
|---|---|
| Understand | `assistant/prompts.py` rule 3. Question ids are `role`, `outcomes`, `tools`, `cadence`; up to 4 questions; multi-select plus free text (`QuestionsForm.tsx`); no brief while role or tools are unknown. |
| Domain research | `research.py` `domain_queries`: integrations per tool, the intersection of two tools, Reddit frustrations, forum problems, GitHub open source, and "what can <role> automate" when outcomes are open. Searches run in parallel; the first community thread, the first open-source project and the first general page are read in full. 60 s budget. |
| Recommend and decide | `PROPOSE_SYSTEM`: intro, findings (each grounded in evidence), 2-3 options, a default, and 0-3 decision questions. The options card shows findings and decisions and sends the answers with the pick. |
| Build research | `research.py` `build_queries`; `service._build_research` runs once after the pick; the turn prompt's BUILD RESEARCH section puts useful APIs and projects into the brief's constraints (rule 3b). |
| Builder | `creation.build_instructions` passes the goal, "What the person told Alpha" (requirements) and "Defaults chosen" (reversible). `PACKAGE_CONTRACT` tells the builder to read the named projects and APIs first, under a clean-room rule with provenance. |
| Screen | `NewProjectPage.tsx`, `CreationOnPage.tsx`, `AssistantPanel` `sendNow` / `cardsOnPage`. |

## Differences from Bridge

| Area | Bridge | Alpha before | Alpha now |
|---|---|---|---|
| Who it's for | Asked; e.g. "professor" changed the whole design | Assumed (student) | Asked first, never guessed |
| Outcomes | Asked as domain questions | Assumed (better grades) | Optional, with "show me what's possible" |
| Current software | Asked, and which software should feed it | Not asked ("manual entry" assumed) | Asked; research looks at how those tools connect |
| Question format | Numbered tap options, "Other" last, "(pick all that apply)" for multi-select | 3 single-choice radios | Up to 4 multi-select questions, each with free text |
| Close every layer | When a source or automatic step is picked, one more round names concrete candidates | No | Ported (rule 3) |
| Look it up, don't ask | Standard fields and statuses are researched, never asked | Defaults chosen silently | Ported: never ask a question with a published answer |
| Prior art | Commons first, then installed modules, then open source | Other projects read only as data | Existing projects are offered first ("extend it") |
| Research | Hard gate; about 4 fetches; the fetcher writes the citation row | 2 generic searches after the brief | Phase-specific queries before options, plus build research after the pick |
| Grounding | "No finding, no proposal"; each proposal revises a named answer and says what it costs | None | Ported into the options prompt |
| Lineage review | A separate read-only reviewer blocks plan items with no lineage | None | A prompt rule: every part of the brief traces to an answer, a finding or a standard expectation. A separate reviewer is not built. |
| Clean room | Provenance recorded, never copy code | None | Ported into the builder contract |
| Plain language | Banned internal words; outcome first, then five short lines at most | Partial (exec copy) | Ported (rule 6) |
| Scope discipline | "Extra tables nobody asked for are scope, not generosity" | Leaned generous | Ported (rule 9) |
| After the build | Installed, made visible, then a short onboarding turn | Make it, then open | Unchanged (gap) |

## Not ported yet (each needs a decision or more than a prompt)

- **A separate lineage reviewer.** Bridge's governance module is read-only and blocks plan
  items with no lineage. Alpha has the rule only inside the prompt.
- **Citations recorded by the fetcher.** Bridge's fetcher writes the citation row itself, so a
  model can't claim a source it never read. Alpha passes evidence as text.
- **An onboarding turn after install.** "Nothing is read or sent until you say yes; shall we add
  the first few together?"
- **Live evaluation fixtures.** Proposal Part A suggests 6 vague and 6 specific requests, run
  nightly on a live model.
