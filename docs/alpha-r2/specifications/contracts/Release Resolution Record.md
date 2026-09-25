# Release resolution

Baseline R2 · contract 0.2. Current Release Specification section 5 owns normative fields.

A resolution record binds an App Version to configuration, logical resources, current connection/grant references, model/budget profile, execution placement and compatible data schema. It includes validation evidence and expected current release for activation. No embedded credential or arbitrary source-provided authority is accepted.

Activation verifies byte identity, the exact installed dependency profile and supported interfaces, current grants, required bindings and schema compatibility, then atomically changes the App's pointer using expected-current comparison. A stale build fails visibly. Migrations use a write fence and recoverable journal before activation. Existing runs keep their snapshot but still obey current revocation.

Settings changes can create a new resolved release without rebuilding code when allowed by config schema. Code rollback selects a compatible older Version with current configuration/grants; it does not revive revoked authority or restore old user data. Restoring a database is a separate reviewed operation.

A shared dependency fix follows Implementation Blueprint section 10: identify consumers, rebuild candidates, verify independently and activate per App. Failed candidates preserve current releases and data. Runs retain exact profile leases; active/candidate/rollback references prevent cleanup. Sharing a profile never shares resolved configuration, credentials or data authority.
