"""Settings -> Models over the real transport: a real Core process answers the connection
routes behind loopback auth, from the `claude` it finds on its builder PATH (a script here)."""

from __future__ import annotations

import stat
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from tests.integration.conftest import CoreProcess, start_core

pytestmark = pytest.mark.integration

FLAGS = (
    "--allowedTools --json-schema --max-budget-usd --model --no-session-persistence "
    "--output-format --permission-mode --permission-prompts --restricted --setting-sources "
    "--strict-mcp-config --system-prompt --tools --verbose"
)
FAKE = f"""#!/bin/sh
case "$1" in
  --version) echo "2.1.283 (Claude Code)" ;;
  --help) for f in {FLAGS}; do echo "  $f"; done ;;
  auth) echo '{{"loggedIn":false,"authMethod":"none"}}'; exit 1 ;;
  -p) echo '{{"type":"result","is_error":true,"result":"Not logged in"}}' ;;
esac
"""


@pytest.fixture
def signed_out_core(tmp_path: Path) -> Iterator[CoreProcess]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(FAKE, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    data = tmp_path / "data"
    data.mkdir()
    core = start_core(
        data,
        routes="fake,claude-code-cli",
        extra_env={"ALPHA_BUILDER_PATH": f"{bin_dir}:/usr/bin:/bin"},
    )
    yield core
    core.stop()


def test_connection_routes_need_the_session_token(signed_out_core: CoreProcess) -> None:
    for method, path in (
        ("GET", "/api/models/connection"),
        ("POST", "/api/models/connection/check"),
        ("POST", "/api/models/connection/login"),
    ):
        response = httpx.request(method, f"{signed_out_core.base_url}{path}", timeout=5)
        assert response.status_code == 401, path


def test_signed_out_is_reported_and_a_check_says_why(signed_out_core: CoreProcess) -> None:
    with signed_out_core.client() as client:
        snap = client.get("/api/models/connection").json()
        assert snap["status"] == "signed_out"
        assert snap["cli_version"] == "2.1.283" and snap["missing_flags"] == []
        assert "claude auth login" in snap["fix"]
        checked = client.post("/api/models/connection/check", timeout=30).json()
        assert checked["check"] == {
            "ok": False,
            "code": "cli_not_logged_in",
            "error": checked["check"]["error"],
        }
        assert checked["status"] == "signed_out"
