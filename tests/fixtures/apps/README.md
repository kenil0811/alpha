# Neutral fixture Apps (F05)

Two small, domain-neutral Apps used by the F05 integration tests. They are not product examples
and contain no job, calorie or other exemplar-domain logic.

- `items_app`: a general list of items with categories, quantities, dates, a unique code, notes
  that reference items, model-estimated quantities, a CSV report artifact and probes that try to
  bypass the platform through the raw SDK channel.
- `tally_app`: a minimal tally that declares `records` and `artifacts` (not `models`) and reuses the
  collection name `items`, so tests can show two Apps with same-named collections stay separate.

`app.yaml.template` contains `{{RUNTIME_PROFILE}}`; tests substitute the exact profile ID that the
trusted build path produced before installing (the builder template does the same in F07/F08).
