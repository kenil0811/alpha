"""F01.C03: missing/wrong IPC credentials and unapproved origins fail."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.conftest import CoreProcess

pytestmark = pytest.mark.integration


def test_missing_token_is_unauthorized(core: CoreProcess) -> None:
    response = httpx.get(f"{core.base_url}/api/health", timeout=5)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert response.json() == {"error": "unauthorized"}


def test_wrong_token_is_unauthorized(core: CoreProcess) -> None:
    with core.client(token="0" * 64) as client:
        assert client.get("/api/health").status_code == 401
        assert client.post("/api/runs", json={"text": "x"}).status_code == 401


def test_malformed_authorization_scheme_is_unauthorized(core: CoreProcess) -> None:
    response = httpx.get(
        f"{core.base_url}/api/health", headers={"Authorization": f"Token {core.token}"}, timeout=5
    )
    assert response.status_code == 401


def test_unapproved_origin_is_forbidden_even_with_token(core: CoreProcess) -> None:
    with core.client(origin="http://evil.example") as client:
        response = client.get("/api/health")
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_origin"}
    with core.client(origin="null") as client:
        assert client.post("/api/runs", json={"text": "x"}).status_code == 403


def test_approved_origin_and_token_succeed(core: CoreProcess) -> None:
    with core.client(origin=core.allowed_origin) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["contract_version"] == "0.2"
    assert body["worker_profiles"] == ["app", "builder", "candidate_runner", "synthetic"]


def test_non_loopback_host_header_is_forbidden(core: CoreProcess) -> None:
    with core.client() as client:
        response = client.get("/api/health", headers={"Host": "alpha.example.com"})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_host"}


def test_non_api_paths_do_not_exist(core: CoreProcess) -> None:
    assert httpx.get(f"{core.base_url}/docs", timeout=5).status_code == 404
    assert httpx.get(f"{core.base_url}/openapi.json", timeout=5).status_code == 404


def test_core_refuses_to_start_without_credentials(data_dir: object) -> None:
    import subprocess
    import sys

    from tests.integration.conftest import REPO_ROOT

    result = subprocess.run(
        [sys.executable, "-m", "alpha.main"],
        env={"ALPHA_DATA_DIR": str(data_dir), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=20,
    )
    assert result.returncode == 2
    assert result.stdout.startswith("ALPHA_CORE_ERROR ")


def test_cors_preflight_only_for_approved_origin(core: CoreProcess) -> None:
    approved = httpx.options(
        f"{core.base_url}/api/runs",
        headers={
            "Origin": core.allowed_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
        timeout=5,
    )
    assert approved.status_code == 200
    assert approved.headers["access-control-allow-origin"] == core.allowed_origin
    assert "authorization" in approved.headers["access-control-allow-headers"].lower()

    unapproved = httpx.options(
        f"{core.base_url}/api/runs",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
        timeout=5,
    )
    assert unapproved.status_code in (400, 403)
    assert "access-control-allow-origin" not in unapproved.headers


def test_actual_response_carries_cors_header_only_for_approved_origin(core: CoreProcess) -> None:
    with core.client(origin=core.allowed_origin) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == core.allowed_origin
    with core.client() as client:
        response = client.get("/api/health")
    assert "access-control-allow-origin" not in response.headers
