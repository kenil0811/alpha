# The App package (contract 0.2), for the builder

An App is a folder the platform seals into an immutable Version:

```
app.yaml        what the App is: data, actions, screen, profile identities
src/            Python action handlers (import only the standard library, alpha_sdk, own modules)
ui/src/         optional screen: main.tsx plus its own .ts/.tsx/.css/.json files
tests/          optional unittest tests (supplementary; the platform's own checks decide)
README.md       optional
```

Nothing else. The package must not contain dependency or lock files (requirements.txt,
pyproject.toml, package.json, *.lock), environment files (.env), `dist/`, `dependencies/`,
symbolic links or executable files. The platform compiles the screen, resolves every dependency
and writes the index and dependency manifest itself.

## app.yaml

```yaml
contract_version: "0.2"
app_id: meal-log              # lowercase letters, digits, - or _; 3–64 characters
name: Meal log                # the person's words
description: One sentence saying what it does for the person.
runtime_profile: pyprof-…     # exact value given by the platform; never change it
sdk_version: 0.1.0            # exact value given by the platform
capabilities: [records]       # records, artifacts, models: only what the actions use
collections: [...]
actions: [...]
ui: {...}                     # optional
```

Unknown fields are rejected. The package cannot name grants, secrets, credentials, local paths
or releases. `modules` must stay empty: extra Python packages are not available.

### collections

```yaml
collections:
  - name: meals                         # lowercase identifier
    description: One eaten meal.
    fields:
      - {name: title, kind: text, required: true, max_length: 200}
      - {name: calories, kind: number, minimum: 0, maximum: 10000}
      - {name: servings, kind: integer, minimum: 1}
      - {name: kind, kind: choice, required: true, choices: [breakfast, lunch, dinner, snack]}
      - {name: eaten_on, kind: date, required: true}          # "YYYY-MM-DD"
      - {name: logged_at, kind: datetime}                     # ISO 8601 with offset
      - {name: done, kind: boolean}
      - {name: meal, kind: reference, collection: meals}      # id of a record in a collection
      - {name: extra, kind: json, max_bytes: 4096}
    indexes: [[eaten_on]]
    unique: [[title, eaten_on]]
```

Every record also has `id`, `revision`, `created_at` and `updated_at`; do not declare them.
Declaring any collection requires the `records` capability.

### actions

```yaml
actions:
  - id: add_meal                          # lowercase identifier, unique
    title: Add a meal
    description: Save one meal eaten today unless another day is given.
    handler: meal_log.handlers:add_meal   # module:function inside src/
    invocable_from: [ui, manual]          # any of ui, manual, assistant, trigger
    effect_class: local_write             # none | local_write | external_read | external_write
    capability_requirements: [records]    # a subset of capabilities
    timeout_seconds: 30                   # 1–300
    retry_class: pure                     # pure | idempotent | requires_reconciliation
    input_schema:                         # JSON Schema object; every required name declared
      type: object
      required: [title]
      additionalProperties: false
      properties:
        title: {type: string, minLength: 1}
        calories: {type: [number, "null"]}
    output_schema:
      type: object
      required: [id, revision]
      properties: {id: {type: string}, revision: {type: integer}}
```

The handler is `def add_meal(ctx, title, calories=None) -> dict`: the Context first, then one
keyword parameter per input property. A parameter without a default must be required by the
input schema, and every declared property must be accepted. The input is checked against
`input_schema` before the handler runs and the result against `output_schema` before the run can
succeed. An action that reads or writes records must list `records` in
`capability_requirements`.

### ui (the screen)

```yaml
ui:
  entry: ui/src/main.tsx
  build_profile: uiprof-…       # exact values given by the platform
  kit_version: 0.1.0
  bridge_version: 0.2.0
  views:                        # everything the screen may read
    - id: meals.recent
      collection: meals
      fields: [title, calories, eaten_on]
      filterable: [eaten_on, kind]
      sortable: [eaten_on, created_at]
      default_order: [{field: created_at, direction: desc}]
      max_limit: 100
    - id: meals.by_day
      kind: aggregate
      collection: meals
      group_by: [{field: eaten_on}]
      metrics: [{name: total, fn: sum, field: calories}, {name: meals, fn: count}]
  actions: [add_meal]           # everything the screen may run; each lists ui in invocable_from
```

A view reads one collection. It may fix a base filter (`where`) and the returned `fields`; the
screen can only narrow it with filters on `filterable` fields and sort on `sortable` fields.
Aggregate views take `group_by` (field, optional `bucket` day/week/month) and `metrics`
(count, sum, avg, min, max). The screen runs actions only through `ui.actions`.

The screen is type-checked with TypeScript (strict) against the kit's own types before it is
built: every required prop must be given, and a type error fails the build with the exact line.

Say each thing once and in the person's words. `QuickEntry` and `Form` already announce their
own saved or failed outcome, so do not add a second status line for the same event. Label a
yes/no value by what it means in both states (a "Finished" column shows "Yes" or "Not yet", never
an unrelated word). Mark values that came from a model estimate as estimates.

An App without a screen leaves `ui` out; its actions are run by the person or the assistant.
