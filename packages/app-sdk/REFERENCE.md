# alpha_sdk reference (for generated App code)

Handlers import only the Python standard library, `alpha_sdk` and the package's own modules.
They have no files, network, subprocesses, environment variables or credentials; everything
goes through the Context the platform passes as the first argument.

```python
from typing import Any

from alpha_sdk import Context, Conflict, NotFound
from alpha_sdk.query import eq, gte, all_of, by_day, total, count


def add_meal(ctx: Context, title: str, calories: float | None = None) -> dict[str, Any]:
    record = ctx.records.create(
        "meals", {"title": title.strip(), "calories": calories, "eaten_on": ctx.today().isoformat()}
    )
    return {"id": record.id, "revision": record.revision}
```

Return a JSON object matching the action's `output_schema`. Raise an exception only for real
failures; the run then fails and the person sees why.

## Context

| Member | Meaning |
|---|---|
| `ctx.records` | the App's own collections (below) |
| `ctx.artifacts` | immutable output files |
| `ctx.models` | bounded structured model calls; results are labelled estimates |
| `ctx.today()` | today's `date` in the person's timezone |
| `ctx.now()`, `ctx.local_now()` | current `datetime` in UTC / the person's timezone |
| `ctx.timezone` | the person's IANA timezone name |
| `ctx.log(message, **data)` | a progress note on the run |

## Records

Values are plain Python: text `str`, number `float`/`int`, integer `int`, boolean `bool`,
date `"YYYY-MM-DD"` string, datetime ISO 8601 string, choice `str`, reference record id, json.
A `Record` has `id`, `revision`, `values` (dict), `provenance`, `created_at`, `updated_at`, and
`record.get(name)`.

```python
ctx.records.create(collection, values, *, idempotency_key=None, estimated=None) -> Record
ctx.records.get(collection, record_id) -> Record                      # NotFound if missing
ctx.records.update(collection, record_id, *, expected_revision, changes) -> Record
ctx.records.correct(collection, record_id, *, expected_revision, changes) -> Record
ctx.records.delete(collection, record_id, *, expected_revision) -> None
ctx.records.query(collection, *, where=None, order_by=None, limit=100, cursor=None) -> Page
ctx.records.all(collection, *, where=None, order_by=None) -> list[Record]
ctx.records.aggregate(collection, *, metrics, group_by=None, where=None) -> Aggregation
batch = ctx.records.batch(); batch.create(...); batch.update(...); batch.commit()  # all or none
```

- `expected_revision` is the revision the person saw; a newer change raises `Conflict`
  instead of being overwritten.
- `correct` records a person's correction of a model estimate (only from ui/manual runs).
- `order_by=["-eaten_on", "title"]`: a leading `-` sorts descending.
- `Page` has `records` and `next_cursor`. `Aggregation` has `groups` (each with `key` and
  `values` dicts) and `truncated`.

Filters (`alpha_sdk.query`): `eq, ne, lt, lte, gt, gte, one_of, contains, starts_with,
is_empty, is_set, all_of, any_of, not_`; combine with `&`, `|` and `~`.
Metrics: `count(), total(field), average(field), smallest(field), largest(field)`.
Grouping: a field name, or `by_day(field)`, `by_week(field)`, `by_month(field)`.

```python
day = ctx.today().isoformat()
page = ctx.records.query("meals", where=eq("eaten_on", day), order_by=["-created_at"])
summary = ctx.records.aggregate(
    "meals",
    metrics={"calories": total("calories"), "meals": count()},
    group_by=[by_day("eaten_on")],
)
```

## Model estimates

```python
guess = ctx.models.structured(
    "Estimate the calories in this meal.",
    input={"meal": title},
    fields={"calories": {"kind": "number", "minimum": 0, "maximum": 5000, "required": True}},
)
ctx.records.create(
    "meals", {"title": title, "calories": guess["calories"]}, estimated={"calories": guess}
)
```

`fields` use the same field kinds as collections. Pass the result in `estimated` so the saved
value is labelled an estimate the person can correct. At most 10 model calls per run.

## Artifacts

```python
ref = ctx.artifacts.create("Weekly summary.csv", csv_text, media_type="text/csv")
ctx.artifacts.read_text(ref.id)
```

## Failures

`OperationError` subclasses: `InvalidValue` (a value the collection rejects), `NotFound`,
`Conflict` (stale revision, taken unique value), `Forbidden` (capability not declared),
`LimitExceeded`, `Unavailable`. Each has `code`, `message` and `details`.
