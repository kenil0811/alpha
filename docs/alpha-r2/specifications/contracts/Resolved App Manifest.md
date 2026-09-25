# Resolved App manifest

Baseline R2 · contract 0.2. Current Release Specification sections 3–5 own the source, Version and Release fields.

Core produces the resolved manifest after validating source and actual callable bindings. It includes dependency_manifest exactly as defined in Current Release Specification section 11, actions and schemas, optional compiled UI assets, collection schema versions and source/asset digests. Core verifies exact profiles and the full package closure; it does not infer compatibility from a friendly name or version range. SDK/UI/module changes create new candidates and do not hot-replace dependencies of existing Versions. It describes executable compatibility, not account authority.

Builder-authored resolved metadata is untrusted input and cannot bypass verification. Resolve handlers in a disposable worker; reject missing symbols, incompatible signatures or mismatched outputs. The activated Release separately resolves configuration/resources/grants and never stores secret bytes in this manifest.

Verification must reference the exact same package digest that is sealed and activated. A stale or different candidate's report cannot certify a modified package.
