# Generated package layout

Baseline R2 · contract 0.2. Source fields are in Current Release Specification section 3.

| Path | Meaning |
|---|---|
| `app.yaml` | Declarative source contract |
| `src/` | Generated Python behavior importing the supported SDK |
| `ui/` | Optional generated React source |
| `tests/` | Candidate-authored supplemental tests, never the only acceptance evidence |
| `dependency.manifest.json` | Platform-produced resolved pins/profile identities from release specification section 11 |
| `dependencies/uv.lock` | Exact managed Python profile lock copied as provenance; no per-App mutable installation |
| `ui/package.json` and `dependencies/pnpm-lock.yaml` | Optional exact build inputs from the managed UI profile; generated code cannot choose floating versions |
| `dist/ui/` | Platform-built optional static UI output |
| `package.index.json` | Platform-produced file digests, toolchain and compatibility manifest |

A sealed Version includes immutable source, compiled UI and trusted validation/resolution metadata, including exact profile/SDK/kit/module digests. Common installed environments and package-manager caches are referenced, not copied into every package. The host resolves them from its inventory. Export/restore must supply compatible exact artifacts as described in the persistence model. Mutable records, artifacts, browser profiles, credentials, environment files and selected user files are excluded. Do not publish absolute device paths. Reject traversal, symlinks escaping the root, undeclared executable assets and unsupported dependency scripts. The platform computes digests after validation and rechecks before activation.

No per-App Python web server, native binary bundle or alternative frontend framework in the initial profile. Rich behavior is possible through Python/React plus qualified capabilities. A package boundary must not be confused with OS containment.
