# HTTP action profile

Baseline R2 · contract 0.2. Describes provider qualification; normative effect semantics are in Current Release Specification section 7. The old JSON schema is reference-only.

Each profile declares `profile_id`, version, allowed scheme/hosts/ports/path patterns, methods, input/header/query/body schemas, response schema/size/time limits, connection injection strategy, effect class, approval policy, idempotency support, receipt extraction and reconciliation procedure. Secret headers are injected by the provider and redacted from evidence. Generated code gets structured results.

Recheck every redirect and resolved destination; block private/loopback/metadata targets unless explicitly required by a narrowly qualified internal profile. Limit redirect count and response expansion. Do not forward authorization to a different origin implicitly. DNS/address checks must occur at actual connection, not only initial URL parsing.

GET is not a guarantee of harmless behavior; method/path semantics and the qualified workflow determine effect policy. Unknown write behavior must be treated conservatively. Broad user-authorized source read scopes can cover repeated retrieval without repeated prompts, but cannot authorize arbitrary account actions.

The first profile supports public retrieval and scoped structured APIs. Inbound public webhooks are outside R2. A new API may use the generic broker within existing scope; unsupported authentication, receipt or effect behavior needs a reusable provider extension rather than fabricated success.
