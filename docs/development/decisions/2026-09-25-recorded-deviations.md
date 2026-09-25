# Decision: deviations from the Implementation Blueprint found in the pre-F07 review

Date: 2026-09-25. Recorded by the coding agent after the founder asked for a plan-alignment review
before F07. No bundle document is modified. Each item was already true in the code; this record
states what differs from the plan, why, what holds the difference in check, and when it is
revisited.

## 1. Model calls use ModelGateway structured calls, not Pydantic AI

**Plan:** Blueprint §1 and Current Architecture Decisions D08 put the assistant and runtime model
loop on Pydantic AI behind ModelGateway.

**Code:** `alpha/models/structured.py` makes one bounded structured call per turn through a
ModelGateway route. The live route runs the Claude Code CLI non-agentically: no tools, one turn,
settings ignored, and a JSON schema. The caller's Pydantic contract model validates the result.
The assistant (F04) and `ctx.models` (F05) both use it.

**Why:** the only live route is the founder's Claude subscription through the CLI (decision
2026-09-25, builder route). Pydantic AI's model providers call provider HTTP APIs with a key,
which this route does not have. Nothing the plan wants from Pydantic AI is lost yet:
- Neither loop calls tools. The assistant proposes a brief; runtime calls return one object.
- Outputs are typed by the contract models.
- Routes, budgets and usage stay in ModelGateway.

**Revisit:** when the first BYOK provider route exists (F22 names the second one). Put Pydantic AI
behind ModelGateway for key-based routes then, or record why not. The assistant has no
schema-repair retry today: an invalid structured answer fails the turn and the failure is kept.

## 2. The capability broker lives in `execution/`, not `capabilities/`

**Plan:** the repository map gives `capabilities/` authorization, grants and provider dispatch.

**Code:** `alpha/execution/broker.py` authenticates worker calls, checks the declared families and
dispatches to the record, artifact and model services. `capabilities/` holds the catalog and the
shared failure type.

**Why:** in F05 the broker is part of the App run lifecycle. It issues tokens at launch, answers
on the run's own pipe and revokes tokens when the worker exits, and the coordinator drives all
three.

**Revisit:** F13 adds grants and external providers. Move authorization and dispatch into
`capabilities/` then, and leave only the pipe handling in `execution/`.

## 3. The App registry lives in `data/`, not `solutions/`

**Plan:** `solutions/` owns Apps, versions, releases and configuration from F08/F10.

**Code:** `alpha/data/apps.py` holds the minimum ownership records and Version sealing that F05
needed to run Apps.

**Revisit:** F08 creates `solutions/` for activation and delivery. Move the registry there in the
same change; `data/` keeps records.

## 4. Builder and candidate processes are Core modules, not `workers/builder` and `workers/validator`

**Plan:** the repository map has `workers/builder` (F02) and `workers/validator` (F07) as separate
worker packages.

**Code:** `alpha/workers/builder.py` and `alpha/workers/candidate_runner.py` run on Core's
interpreter. The builder imports the harness adapters from `alpha/builds`.

**Why this is only partly acceptable:**
- The builder is trusted platform code that drives the CLI. Running it on the platform
  interpreter is acceptable for now.
- The candidate runner is not acceptable. It executes generated code where Core is importable,
  and the specification requires a disposable worker on the exact App profile.

**Revisit:**
- **F07:** move candidate checks to `workers/validator` running on the sealed App runtime
  profile, and use the App package format `AppRegistry.install` accepts.
- **F20:** qualify the builder profile with the sandbox; moving the builder to `workers/builder`
  can happen then.

## 5. The UI bridge types are written by hand, not generated

**Plan:** App UI Bridge says to generate the typed definitions during F03/F06.

**Code:** `packages/ui-bridge/src/protocol.ts` defines the message types by hand. The Python
contracts have no bridge models to generate from.

**Held in check by:**
- The host checks every message at runtime:
  - It refuses unknown envelope fields.
  - `records.query` refuses unknown payload keys.
  - Action and observe requests forward only the fields they name.
- The payload parts that repeat contract shapes are compared with the generated contract types
  at type-check time, in `packages/ui-bridge/src/contracts.test-d.ts`.
- The kit's copies of the record, filter and provenance shapes get the same check in
  `packages/ui-kit/src/data/contracts.test-d.ts`.

**Revisit:** F08 is when the shell serves real App UI. Add bridge models to `packages/contracts`
and generate the TypeScript if the protocol grows beyond today's six request types.

## 6. The App SDK is standard library only and does not depend on contracts

**Plan:** Blueprint §3 says the SDK and UI bridge depend on contracts.

**Code:** `alpha-sdk` has no dependencies. It keeps its own copies of the protocol version,
operation names and failure codes.

**Why:** the SDK is installed into every App runtime profile. Depending on `alpha-contracts` would
bring Pydantic and its compiled core into generated code's environment. The F05 profile
deliberately contains no third-party package (decision 2026-09-25, F05 §2).

**Held in check by:** `packages/app-sdk/tests/test_contract_sync.py`, which fails when:
- the protocol version differs from the contract's;
- the SDK sends an operation the contract lacks, or misses one it has;
- a contract failure code does not reach handlers unchanged.

On Core's side, the failure codes are imported from the contract. `services/core/tests/test_protocol_sync.py`
checks that every code has an HTTP status and every contract operation reaches a broker handler.

## 7. The capability catalog lists families and reasons only

**Plan:** Blueprint §3 says the catalog also carries:
- operation descriptions and schemas;
- connection types and required grants;
- supported profile versions.

**Code:** each family has a description, availability and, when unavailable, a reason and the
ticket it arrives with. Only `compute` is available to generated solutions.

**Revisit:** F08 makes records, artifacts, runtime model calls and custom UI available. Add each
family's operation schemas and the runtime and UI profile versions then, because the builder
needs them to plan.
