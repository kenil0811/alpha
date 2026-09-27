# ruff: noqa: E501
"""Alpha's default taste for modules, in plain sentences. Shipped as the default value of the
"Rules for how modules should look and behave" setting, so the person can read it, edit it or
reset it; the builder, the quick-change editor and the verifier follow whatever is set."""

DEFAULT_CONVENTIONS = """\
Lead with what the person came for. When a module keeps a list of things, the working table or board comes first on the main tab; a one-line quick entry sits above it only when typing a line is the main way things get in. Manual forms come after the data and start folded.
One subject per tab, named by what it shows (Openings, Sources, Goals), never by a verb. Four tabs at most; the first is the one used every day.
Every table has a detail page, an Added time, saved lists for its statuses and quick filters for its choices. Columns are the five or six the person scans; the rest live on the detail page.
Freshness is visible: when something was added or last changed, when a source was last read and when the next check runs.
Summaries come after the data: at most four metric cards, then a trend when numbers change over time.
Plain words, sentence case, no jargon and no emoji in labels. Numbers carry their unit. Dates read as 27 Sep, times in the person's local time.
Compact. No decorative headings or explanatory panels above the data; one short empty-state line that says what to do next.
Anything that runs on its own is visible under Automations with an on/off switch, and every action answers in one sentence saying what happened.
Estimates are labelled as estimates and can be corrected in place.
Nothing is invented: when a source cannot be read or a value is unknown, say so and store nothing made up.
"""
