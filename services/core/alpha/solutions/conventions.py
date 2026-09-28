# ruff: noqa: E501
"""Alpha's default taste for modules, in plain sentences. Shipped as the default value of the
"Rules for how modules should look and behave" setting, so the person can read it, edit it or
reset it; the builder, the quick-change editor and the verifier follow whatever is set."""

DEFAULT_CONVENTIONS = """\
Every table the module keeps is a page of its own, drawn by Alpha the same way everywhere: a table first, with board, list, calendar and chart a click away, a record page for each row, and edits in place. Do not design screens; declare the tables well: a title field, a status field with its finished values, the columns the person scans first, and a quick entry above the table when typing one line is the main way things get in.
A Summary tab with the numbers that matter (at most four cards, a progress bar against a goal, a trend when numbers change over time) comes first when the module has numbers worth a glance; otherwise the main table is the first tab.
One subject per page, named by what it holds (Openings, Sources, Goals), never by a verb. Five pages at most.
Freshness is visible: when something was added or last changed, when a source was last read and when the next check runs.
Summaries come after the data: at most four metric cards, then a trend when numbers change over time.
Plain words, sentence case, no jargon and no emoji in labels. Numbers carry their unit. Dates read as 27 Sep, times in the person's local time.
Compact. No decorative headings or explanatory panels above the data; one short empty-state line that says what to do next.
Anything that runs on its own is visible under Automations with an on/off switch, and every action answers in one sentence saying what happened.
Estimates are labelled as estimates and can be corrected in place.
Nothing is invented: when a source cannot be read or a value is unknown, say so and store nothing made up.
"""
