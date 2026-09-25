# Resources, context and integrations

Baseline R2 · 24 September 2026. Owns how shared capabilities are exposed and composed. Payload/effect definitions live in Current Release Specification and Capability Protocol.

## Resources and connections

A Resource is a logical handle to records, an artifact, selected files/folders, a permitted web source or a browser/account context. It records owner, type, provenance and current grants. A Connection is account/provider metadata plus a secure secret reference. Neither is a generic table row carrying all of the user's authority.

Generated packages name their needs; Release/Task resolution binds actual resources under user authority. A copied URL or source string is not a credential. Bind by account/destination/purpose and recheck revocation. Do not copy native paths or session material into portable packages.

## Provider order

The assistant and builder query a platform CapabilityCatalog for currently implemented operations, schemas, limits, available account types and unmet prerequisites. They may propose a new source strategy, but must verify actual access. Search/discovery is itself a capability: until a search provider is qualified, ask for sources or use explicitly supported source locations and explain the coverage. A model-generated URL is not fresh retrieval evidence.

Use an existing qualified connector/API when suitable, generic bounded HTTP for compatible protocols, and the browser provider for UI-only/authenticated sites. New sites do not always require platform releases: generated code can map/extract/compose within available operations. New authentication mechanisms, native privileges or effect semantics require a shared provider extension and conformance evidence.

When a source is unavailable, report whether access, login, capability, eligibility or site behavior is the cause. Do not return seeded data as a substitute for fresh retrieval. Retain source URL/record ID, fetched time, content digest where practical and extraction provenance.

## First capability families

| Family | Initial operations | Boundary |
|---|---|---|
| Records | Query/aggregate/create/patch/delete/batch | Schema, owner, revision and idempotency checks |
| Artifacts | Read/create/preview/export | Scoped handles, limits and selected output location |
| Models | Structured inference/classification/extraction | Named route, selected context, usage/budget and validated result |
| Files | Selected read/list/write/export profiles | Explicit handle/mode; complex parsing isolated |
| HTTP | Bounded reads and qualified action profiles | Destination/redirect/auth/effect/receipt policy |
| Browser | Navigate/inspect/extract/fill/selected upload/download/takeover | Dedicated session, current page/account, qualified effects and evidence |

An action can combine deterministic logic and bounded runtime model calls. Validate structured output and preserve decisions before a consequential step. Do not put an LLM in every loop when simple rules suffice. A declared expected schema cannot make uncertain external facts true; preserve provenance and allow correction.

## Browser interaction detail

Use semantic locators and inspect returned elements/values; cap pages/time and retain useful sanitized evidence. Source changes may invalidate selectors. A provider error should identify a repairable failure with context rather than hide it behind an empty list. Isolate contexts by account/workflow scope and avoid concurrent conflicting tabs in a shared form operation.

Navigation and inspection use approved source scopes. Clicks, fills, uploads and submissions have qualified effect semantics; unknown autosave behavior is surfaced or handed off. Never expose unrestricted page-evaluation code as a back door to account effects. CAPTCHA/MFA/login expiry request visible user takeover. Supported form automation fills supplied facts, identifies missing information, reviews actual values and distinguishes prepared from submitted.

## Source refresh and user ownership

Keep external identifiers and normalized source projection separate from user notes/status/overrides. Ingestion can update source facts but cannot reset user decisions. Use explicit merge rules, atomic revisions and uniqueness keys. Deletions/unavailable source items should be marked with provenance rather than destroying useful user history automatically.

## Capability growth

Each extension packet includes user value, operations/schemas, effect classes, authentication/grants, limits, evidence, failure/reconciliation, package/runtime compatibility and tests. MCP may be an adapter transport for a future vetted connector; an arbitrary server/tool listing does not become trusted authority by installation. Voice, screen, audio synthesis, desktop actions and public webhooks are later qualified capabilities, not hidden requirements of the first generic runtime.
