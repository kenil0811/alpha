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
| `ctx.web` | public web pages and search (the `http` capability; below) |
| `ctx.profile` | what Alpha knows about the person, shared by all their modules (the `profile` capability; below) |
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
value is labelled an estimate the person can correct.

Batch work (scoring, summarising or extracting many items) is ONE call, not one per item: put
the items in `input` (up to ~60 KB) and ask for a `json` field that holds a list with one entry
per item, saying the exact keys in the instruction, for example
`fields={"scores": {"kind": "json", "required": True}}` and "return under scores a list of
objects with keys ref, match_level (Strong, Possible or Weak) and match_reason". The answer may
be up to 64 KB; check each entry's keys before you trust it, and keep the item's `ref` so you can
match answers back to items.

When no estimate is available, `ctx.models.structured` raises `Unavailable` (or an
`OperationError` with code `timed_out`). Never replace it with a guess or a default number:
either save the value as unknown (`None`) and let the screen say "not estimated", or refuse with a
plain message asking the person to type the value. Verification makes the model fail on purpose
and rejects an App that stores a made-up number. At most 10 model calls per run. A call
usually takes a few seconds; give an action that makes several calls `timeout_seconds: 120`.

## Artifacts

```python
ref = ctx.artifacts.create("Weekly summary.csv", csv_text, media_type="text/csv")
ctx.artifacts.read_text(ref.id)
```

## Web (`http` capability)

```python
page = ctx.web.get("https://example.com/jobs")  # readable text; page.title, page.status, page.text
page.links  # every link on the page as Link(text, url, near): absolute addresses, in page order;
# near = the text of the card around the link when a browser read the page (name,
# title, company), for links whose own text is empty, such as a photo
data = ctx.web.get("https://api.example.com/v1/x", raw=True)  # a JSON API's body untouched
hits = ctx.web.search("kettlebell beginner routine", count=5)  # [.title, .url, .snippet]
```

A listing page (jobs, products, articles) is best read through `page.links`: keep the links
whose address matches the items (for example those containing `/remote-jobs/` or `/listings/`),
use each link's text as the item's title, and fetch an item's own page only when you need its
details. `page.text` is for reading, not for finding addresses: it carries no hrefs, and site
navigation comes first in it. When items are hard to tell apart by address, pass the relevant
part of `page.text` to `ctx.models` with a schema and let the model list them.

Sites that need a sign-in, and pages drawn by scripts, go through the `browser` capability:
declare `browser` next to `http`. The person connects a site (LinkedIn, Indeed) on Connections,
signing in themselves, and switches it on for this App; from then on `ctx.web.get(url)` for
that site reads through their session with no change to your code, `page.signed_in` is true,
and each page is paced and listed in the App's Activity. For a public page that draws its
content with scripts, pass `rendered=True`. When `page.blocked` is true the site answered with a
sign-in page: say so in the result and store nothing. Never try to log in, click or submit.

Declare `http` in the App's `capabilities` and in the action's `capability_requirements`.
Only public http(s) addresses are fetched (nothing on this Mac or a private network), bodies are
capped at 2 MB, and a run may make at most 60 web requests. Nothing is signed in: pages that need
an account are out of reach. When a fetch fails the call raises `Unavailable`; report that
plainly and store nothing invented. Text you extract from a page is a source, not a fact the
person typed: keep the address it came from alongside what you save.

## Profile (`profile` capability)

```python
roles = ctx.profile.get("target_roles")  # the accepted value, or None
known = ctx.profile.all()  # {field: value} for every accepted fact
ctx.profile.set("degree", "MSc Computer Science")  # what the person typed into this App
ctx.profile.suggest("skills", ["Python", "SQL"], why="from the modules listed in Academics")
```

Facts about the person live in one place and every module can read them, so a job module
knows the coursework an academics module recorded and a diet module knows a goal the person
set elsewhere. `set` passes on what the person told this App (it becomes an accepted fact,
labelled as coming from this App). `suggest` is for what the App worked out: the person sees it
on their About you page and accepts or rejects it; until then reads do not return it. Use plain
snake_case field names another module would also choose (degree, university, skills,
target_roles, location, dietary_goal, weekly_budget), never invent a fact, and prefer the
profile over asking the person for something Alpha already knows. Declare `profile` in the
App's `capabilities` and in the action's `capability_requirements`.

## Failures

`OperationError` subclasses: `InvalidValue` (a value the collection rejects), `NotFound`,
`Conflict` (stale revision, taken unique value), `Forbidden` (capability not declared),
`LimitExceeded`, `Unavailable`. Each has `code`, `message` and `details`.
