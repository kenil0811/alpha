"""Neutral web fixture: read a public page or search, keeping only what came back."""

from __future__ import annotations

from typing import Any

from alpha_sdk import Context


def read_page(ctx: Context, url: str) -> dict[str, Any]:
    page = ctx.web.get(url.strip(), max_chars=4000)
    summary = " ".join(page.text.split())[:600]
    record = ctx.records.create(
        "findings",
        {
            "kind": "page",
            "query": url.strip(),
            "title": page.title or page.final_url,
            "summary": summary,
            "url": page.final_url,
            "fetched_on": ctx.today().isoformat(),
        },
    )
    words = f"Read “{page.title}”" if page.title else f"Read {page.final_url}"
    if not page.ok:
        words += f" (the site answered {page.status})"
    return {
        "id": record.id,
        "revision": record.revision,
        "message": words + ".",
        "title": page.title,
    }


def search_web(ctx: Context, query: str) -> dict[str, Any]:
    hits = ctx.web.search(query.strip(), count=5)
    lines = [f"{h.title} — {h.url}" for h in hits]
    record = ctx.records.create(
        "findings",
        {
            "kind": "search",
            "query": query.strip(),
            "title": f"Search: {query.strip()}",
            "summary": "\n".join(lines)[:2000] if lines else "No results came back.",
            "url": hits[0].url if hits else None,
            "fetched_on": ctx.today().isoformat(),
        },
    )
    message = f"Found {len(hits)} result{'s' if len(hits) != 1 else ''} for “{query.strip()}”."
    return {"id": record.id, "revision": record.revision, "message": message}
