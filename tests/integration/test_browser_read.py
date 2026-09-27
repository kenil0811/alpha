"""The browser worker with a real Chrome: a page drawn by scripts is read after its scripts
ran, with its links; a plain fetch would have seen none of it. Skipped where neither Google
Chrome nor the Playwright Chromium is on this Mac."""

from __future__ import annotations

import http.server
import os
import threading
from pathlib import Path

import pytest
from alpha.capabilities.browser import BrowserService
from alpha.storage.control_store import ControlStore

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
PAGE = b"""<!doctype html><html><head><title>Board</title></head><body>
<div id="jobs">loading</div>
<script>
  document.getElementById('jobs').innerHTML =
    '<a href="/jobs/1">Senior Python Engineer</a><a href="/jobs/2">Data Engineer</a>';
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_: object) -> None:
        return


def browser_present() -> bool:
    cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path("/Applications/Google Chrome.app").exists() or any(cache.glob("chromium-*"))


@pytest.mark.skipif(not browser_present(), reason="no Chrome on this Mac")
def test_a_script_drawn_page_is_read_after_its_scripts_ran(tmp_path: Path) -> None:
    node = Path(os.environ.get("ALPHA_NODE") or "/opt/homebrew/opt/node@24/bin/node")
    if not node.is_file():
        pytest.skip("node is not installed at the pinned path")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        service = BrowserService(
            ControlStore(tmp_path / "control.sqlite"),
            node=node,
            script=REPO / "workers" / "validator" / "src" / "browser_session.mjs",
            root=tmp_path / "browser",
        )
        # The public-address guard refuses loopback for modules; the worker is what this test
        # exercises, so drive it directly.
        result = service._run_worker(  # noqa: SLF001
            {
                "op": "read",
                "url": f"http://127.0.0.1:{port}/board",
                "profile": None,
                "max_chars": 5000,
                "scroll": 0,
                "channel": service._channel,  # noqa: SLF001
            }
        )
        assert result["status"] == 200 and result["title"] == "Board"
        assert "Senior Python Engineer" in result["text"]
        assert [link["text"] for link in result["links"]] == [
            "Senior Python Engineer",
            "Data Engineer",
        ]
        assert result["links"][0]["url"] == f"http://127.0.0.1:{port}/jobs/1"
        assert result["blocked"] is False
    finally:
        server.shutdown()
