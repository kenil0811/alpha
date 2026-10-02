"""Discovery research is aimed at the person's role and tools, then at building the choice."""

from __future__ import annotations

from alpha.assistant.research import build_queries, domain_queries


def test_domain_research_covers_tools_their_intersection_community_and_open_source() -> None:
    told = {"role": "Professor or lecturer; Researcher", "tools": "Canvas; Excel or Google Sheets"}
    queries = domain_queries("an academics project", told)
    assert "Canvas integrations for Professor or lecturer" in queries
    assert any("Canvas and Excel" in q for q in queries)  # work at the intersection
    assert any(q.startswith("reddit ") for q in queries)
    assert any(q.startswith("github open source") for q in queries)
    assert any(q.startswith("what can") for q in queries)  # outcomes left open: explore
    assert len(queries) <= 8


def test_open_outcome_pick_is_not_an_outcome_and_build_research_looks_for_apis() -> None:
    told = {
        "role": "Student",
        "outcomes": "Not sure yet: show me what's possible",
        "tools": "Notion",
    }
    assert any(q.startswith("what can") for q in domain_queries("study planner", told))
    queries = build_queries("study planner", told, 'Go with "Deadline board"')
    assert queries[0].startswith("github open source")
    assert any(q.startswith("Notion API") for q in queries)
