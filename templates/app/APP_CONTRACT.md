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
capabilities: [records]       # records, artifacts, models, http, schedules: only what the actions use
collections: [...]
actions: [...]
views: [...]                  # declared read views
screen: {...}                 # the screen Alpha draws (normal)
ui: {...}                     # a custom compiled screen (rare)
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

### views (what screens may read)

```yaml
views:
  - id: meals.recent                 # letters, digits, _ and one optional dot
    collection: meals
    fields: [title, calories, eaten_on]          # optional projection
    filterable: [eaten_on, kind, title]          # the screen may filter only on these
    sortable: [eaten_on, created_at]             # and sort only on these
    default_order: [{field: created_at, direction: desc}]
    max_limit: 100
  - id: meals.by_day
    kind: aggregate
    collection: meals
    group_by: [{field: eaten_on, bucket: day}]   # a day bucket is returned as eaten_on_day
    metrics: [{name: total, fn: sum, field: calories}, {name: meals, fn: count}]
```

A view reads one collection. It may fix a base filter (`where`) and the returned `fields`; a
screen can only narrow it with filters on `filterable` fields and sort on `sortable` fields.
Aggregate views take `group_by` (field, optional `bucket` day/week/month) and `metrics` (count,
sum, avg, min, max). Put a text field the person will search in `filterable`.

### screen (drawn by Alpha; the normal way to give an App a screen)

Alpha draws a declared screen with its own components, so every module gets the same tables,
quick entry, metrics, trend chart, board, list and forms, and nothing is compiled. Declare tabs
of blocks. Every block reads through a view above and writes through an action whose
`invocable_from` includes `ui`.

```yaml
screen:
  icon: "🍽"                          # one character, optional
  assistant_hint: Meals are logged by typing one line.   # optional, for the assistant
  tabs:
    - id: log
      title: Food log
      blocks:
        - kind: quick_entry           # one line in, one action call; keep it first
          action: log_meal
          input: text                 # the action input that receives the typed line
          placeholder: "What did you eat? e.g. 2 eggs and toast"
        - kind: table
          view: meals.recent
          columns:
            - {field: eaten_on, format: date, title: Day}
            - {field: title, editable: true}
            - {field: calories, format: number, unit: kcal, editable: true}
            - {field: kind, format: pill}
          lists:                      # saved filters offered in a dropdown; {"$today": -6} = six days ago
            - {id: week, title: Last 7 days, where: {field: eaten_on, op: gte, value: {"$today": -6}}}
          edit: {action: correct_meal, id_param: meal}      # a cell edit calls correct_meal(meal=<id>, <field>=<value>)
          delete: {action: correct_meal, id_param: meal, input: {delete: true}}
          row_actions: [{action: duplicate_meal, id_param: meal, title: Again}]
          # The record's own page, opened by clicking a row: every field of the view (or `fields`),
          # long text as paragraphs, when it was added and last changed, and the actions for one
          # record. Every table that tracks things should have one.
          detail: {title_field: food, long_fields: [notes], actions: [{action: correct_meal, id_param: meal, input: {delete: true}, title: Remove}]}
          totals: [calories]          # summed over the rows shown
          empty: Nothing logged yet.
        - kind: metrics
          cards:
            - {title: Calories today, view: meals.by_day, metric: total, unit: kcal, goal: 2000}
            # or a goal the person sets, read from a record: goal_from: {view: goals.current, field: calorie_goal}
            - {title: Meals today, view: meals.by_day, metric: meals}
        - kind: trend
          title: Calories per day
          view: meals.by_day
          x: eaten_on_day             # the day group key
          y: total                    # the metric
          unit: kcal
          goal: 2000
          days: 14
    - id: review
      title: Review
      blocks:
        - kind: board                 # columns from a choice field; moving a card calls an action
          view: meals.recent
          group_field: kind
          columns: [breakfast, lunch, dinner, snack]
          title_field: title
          subtitle_fields: [eaten_on, calories]
          move: {action: correct_meal, id_param: meal}
          field_param: kind
        - kind: list                  # simple rows with a title, subtitles, a badge, a link
          view: meals.recent
          title_field: title
          subtitle_fields: [eaten_on]
          badge_field: kind
          item_actions: [{action: correct_meal, id_param: meal, input: {delete: true}, title: Remove}]
    - id: goals
      title: Goals
      blocks:
        - kind: form                  # one action as a form; prefill_view fills it from a record
          action: set_goal
          title: Daily goal
          prefill_view: goals.current
          submit_label: Save goal
        - kind: text
          title: How this works
          body: Plain words for the person.
```

Prefer a `quick_entry` for the main logging job: its action takes the typed line and does the
whole job itself (parse what it can, estimate the rest through `ctx.models`, save, and return a
`message` in plain words). Do not split "estimate" and "log" into two forms the person has to
copy numbers between. Use `goal_from` (a records view holding the person's goal) so metric
cards and trends compare against what they set, not a fixed number.

Rules the platform checks: every `view` exists; every column, subtitle, title, group and badge
field is in the view's collection (or its `fields`); `edit`/`delete`/`move` name an `id_param`;
a `board`'s `group_field` is a choice field and its `columns` are its choices; a `metrics` card
or `trend` uses an aggregate view and names one of its metrics; `trend.x` is a group key of that
view (`<field>_day` for a day bucket). Actions the screen runs must list `ui` in
`invocable_from`. A metric card over a day-bucketed view shows today's group.

What the shell does with the declaration: the quick entry sends the typed line and shows the
action's `message` output (return a `message` in the person's words); editable cells send
`{id_param: id, <field>: value}` and refresh the views; totals and pagination are automatic;
model estimates are labelled from record provenance.

### schedules (run an action while Alpha is open)

```yaml
capabilities: [records, http, schedules]
schedules:
  - id: check_boards
    title: Check the job boards
    action: check_boards          # must list trigger in invocable_from
    input: {}
    every_minutes: 120            # or daily_at: "21:00" (the person's local time)
    enabled: true
```

Alpha runs the action on time while it is open, shows the last and next run on the module page
with an on/off switch and a "Run now" button, and never catches up missed runs after it was
closed. A scheduled action gets no person to ask: make it self-contained and return a `message`.

### ui (a custom screen, only when no block fits)

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

Unknown is not zero. When a value is missing (a day with no entries, an estimate that could not
be made), keep it unknown and show it as such. An average over days counts only the days with
entries and says how many there were ("1,060 per logged day · 1 of 7 days logged"). A value the
person enters as 0 is a real zero.

Say each thing once and in the person's words. `QuickEntry` and `Form` already announce their
own saved or failed outcome, so do not add a second status line for the same event. Label a
yes/no value by what it means in both states (a "Finished" column shows "Yes" or "Not yet", never
an unrelated word). Mark values that came from a model estimate as estimates.

An App with neither `screen` nor `ui` shows one form for its `primary_action`, the action a
person runs to get the result, and shows what it returns. So:
- set `primary_action` (required without a screen) and give it a clear title and description;
- keep helper steps internal: an action that needs another step's output is not listed as
  `manual`, and the primary action calls your helper functions directly;
- mark a text input the person pastes or writes at length with `multiline: true` in its
  input schema; a list of short texts can be an array of strings (one per line on the form);
- return results as plain data a person can read: a list of entries becomes a table, a list of
  words becomes a list. Name keys in the person's words (`wont_fit`, `total_minutes`); ids are
  not shown.
