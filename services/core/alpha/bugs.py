"""Alpha's own bug log: a markdown file it keeps up to date when Core sees a real failure.

One entry per (area, summary): seeing it again bumps its counter rather than adding a line. An
entry moves to "Fixed" when the same thing later works, and back to "Open" if it returns.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from alpha.storage.control_store import utc_now

HEADER = (
    "# Alpha's bugs\n\n"
    "Alpha maintains this file itself: each failure it notices, once, with how often it was seen.\n"
)
_ENTRY = re.compile(
    r"^- \[(?P<area>[^\]]+)\] (?P<summary>.+) — seen (?P<n>\d+) times?, last (?P<last>\S+)$"
)

Entry = dict[str, str | int]


def _line(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


class BugLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def record(self, area: str, summary: str, detail: str = "") -> None:
        """Note a failure under Open, or count it again when it is already there."""
        area, summary, detail = _line(area, 40), _line(summary, 160), _line(detail, 300)
        if not area or not summary:
            return
        with self._lock:
            open_, fixed = self._load()
            entry = self._pop(open_, area, summary) or self._pop(fixed, area, summary)
            if entry is None:
                entry = {"area": area, "summary": summary, "n": 0, "detail": ""}
            entry["n"] = int(entry["n"]) + 1
            entry["last"] = utc_now().date().isoformat()
            if detail:
                entry["detail"] = detail
            open_.append(entry)
            self._save(open_, fixed)

    def resolve(self, area: str, summary: str) -> None:
        """Move an open entry to Fixed (nothing happens when there is none)."""
        area, summary = _line(area, 40), _line(summary, 160)
        with self._lock:
            open_, fixed = self._load()
            entry = self._pop(open_, area, summary)
            if entry is None:
                return
            fixed.append(entry)
            self._save(open_, fixed)

    def read(self) -> str | None:
        return self.path.read_text(encoding="utf-8") if self.path.is_file() else None

    # ----- the file -----------------------------------------------------------------------

    @staticmethod
    def _pop(entries: list[Entry], area: str, summary: str) -> Entry | None:
        for i, entry in enumerate(entries):
            if entry["area"] == area and entry["summary"] == summary:
                return entries.pop(i)
        return None

    def _load(self) -> tuple[list[Entry], list[Entry]]:
        sections: dict[str, list[Entry]] = {"open": [], "fixed": []}
        current: list[Entry] | None = None
        for raw in (self.read() or "").splitlines():
            if raw.startswith("## "):
                current = sections.get(raw[3:].strip().lower())
                continue
            if current is None:
                continue
            match = _ENTRY.match(raw)
            if match:
                current.append({**match.groupdict(), "detail": ""})
            elif raw.startswith("  ") and current and raw.strip():
                current[-1]["detail"] = raw.strip()
        return sections["open"], sections["fixed"]

    def _save(self, open_: list[Entry], fixed: list[Entry]) -> None:
        lines = [HEADER]
        for title, entries in (("Open", open_), ("Fixed", fixed)):
            lines.append(f"## {title}\n")
            for e in entries:
                times = "time" if int(e["n"]) == 1 else "times"
                lines.append(
                    f"- [{e['area']}] {e['summary']} — seen {e['n']} {times}, last {e['last']}"
                )
                if e["detail"]:
                    lines.append(f"  {e['detail']}")
            lines.append("")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(self.path)
