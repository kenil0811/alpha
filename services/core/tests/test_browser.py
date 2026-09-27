"""The signed-in browser: sites the person connects, what each module may read through them,
pacing per site, and pages recorded for Activity. The worker is a fake here; the real one is a
Node script driving Chromium."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.capabilities.browser import BrowserService, site_key
from alpha.capabilities.errors import OperationFailed
from alpha.storage.control_store import ControlStore
from alpha_contracts.web import HttpGetRequest


@pytest.mark.parametrize(
    ("value", "site"),
    [
        ("LinkedIn.com", "linkedin.com"),
        ("https://www.linkedin.com/jobs/search?x=1", "linkedin.com"),
        ("uk.linkedin.com", "linkedin.com"),
        ("https://www.bbc.co.uk/news", "bbc.co.uk"),
        ("jobs.example.com.au/x", "example.com.au"),
    ],
)
def test_a_site_is_its_registrable_name(value: str, site: str) -> None:
    assert site_key(value) == site


def test_not_a_site_is_refused() -> None:
    with pytest.raises(OperationFailed):
        site_key("not a site")


class FakeWorker:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.signed_in = True

    def __call__(self, job: dict[str, Any]) -> dict[str, Any]:
        self.jobs.append(job)
        if job["op"] == "signin":
            return {"signed_in": self.signed_in, "cookies": 3 if self.signed_in else 0}
        return {
            "status": 200,
            "final_url": job["url"],
            "title": "Jobs",
            "text": "Senior Python Engineer at Acme",
            "links": [
                {"text": "Senior Python Engineer", "url": "https://www.linkedin.com/jobs/view/1"}
            ],
            "truncated": False,
            "blocked": False,
        }


def service(
    tmp_path: Path, worker: FakeWorker, prefs: dict[str, int] | None = None
) -> BrowserService:
    preferences = SimpleNamespace(
        get=lambda key: (prefs or {}).get(
            key, {"browser.pages_per_hour": 30, "browser.min_seconds_between_pages": 15}[key]
        )
    )
    return BrowserService(
        ControlStore(tmp_path / "control.sqlite"),
        node=None,
        script=None,
        root=tmp_path / "browser",
        preferences=preferences,
        runner=worker,
    )


def wait_state(svc: BrowserService, site: str, state: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        found = next((s for s in svc.list_sites() if s["site"] == site), None)
        if found and found["state"] == state:
            return found
        time.sleep(0.02)
    raise AssertionError(f"{site} never became {state}: {svc.list_sites()}")


def test_signing_in_connects_a_site_and_a_module_may_then_read_through_it(tmp_path: Path) -> None:
    worker = FakeWorker()
    svc = service(tmp_path, worker)
    assert svc.available
    started = svc.start_signin("https://www.linkedin.com/login")
    assert started == {"site": "linkedin.com", "state": "signing_in"}
    wait_state(svc, "linkedin.com", "connected")
    assert worker.jobs[0]["op"] == "signin" and worker.jobs[0]["url"] == "https://www.linkedin.com/"
    assert (tmp_path / "browser" / "linkedin.com").is_dir()

    # Nothing may use it until the person switches it on for a module.
    assert svc.allowed_site("job-radar", "https://uk.linkedin.com/jobs/view/1") is None
    with pytest.raises(OperationFailed, match="not signed in to indeed.com"):
        svc.set_grants("job-radar", ["linkedin.com", "indeed.com"])
    assert svc.set_grants("job-radar", ["linkedin.com"]) == ["linkedin.com"]
    assert svc.allowed_site("job-radar", "https://uk.linkedin.com/jobs/view/1") == "linkedin.com"
    assert svc.allowed_site("other-app", "https://uk.linkedin.com/jobs/view/1") is None

    page = svc.read(
        "run_1",
        "job-radar",
        HttpGetRequest(url="https://www.linkedin.com/jobs/search?keywords=python"),
        "linkedin.com",
    )
    assert page.via == "browser" and page.signed_in is True and page.blocked is False
    assert page.links[0].url == "https://www.linkedin.com/jobs/view/1"
    assert worker.jobs[-1]["profile"].endswith("/browser/linkedin.com")
    visits = svc.visits("job-radar")
    assert len(visits) == 1 and visits[0]["site"] == "linkedin.com" and visits[0]["signed_in"] == 1

    svc.remove_site("linkedin.com")
    assert svc.list_sites() == [] and svc.grants("job-radar") == []
    assert not (tmp_path / "browser" / "linkedin.com").exists()


def test_a_closed_window_without_a_session_is_not_connected(tmp_path: Path) -> None:
    worker = FakeWorker()
    worker.signed_in = False
    svc = service(tmp_path, worker)
    svc.start_signin("indeed.com")
    found = wait_state(svc, "indeed.com", "not_connected")
    assert "without a signed-in session" in found["last_error"]
    assert svc.connected_sites() == set()


def test_reading_through_a_session_is_paced(tmp_path: Path) -> None:
    worker = FakeWorker()
    svc = service(
        tmp_path, worker, {"browser.pages_per_hour": 2, "browser.min_seconds_between_pages": 60}
    )
    request = HttpGetRequest(url="https://www.linkedin.com/jobs/view/1")
    svc.read("run_1", "job-radar", request, "linkedin.com")
    with pytest.raises(OperationFailed) as too_soon:
        svc.read("run_1", "job-radar", request, "linkedin.com")
    assert too_soon.value.code == "limit_exceeded" and "too soon" in too_soon.value.message
    # A rendered public page uses no session and is not paced.
    public = svc.read(
        "run_1", "job-radar", HttpGetRequest(url="https://example.com/", rendered=True), None
    )
    assert public.via == "browser" and public.signed_in is False
    assert worker.jobs[-1]["profile"] is None
