"""Routes for the signed-in browser: the sites the person connected, which modules may use
them, and the pages a module opened through them."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from alpha.capabilities.browser import BrowserService
from alpha.capabilities.errors import HTTP_STATUS, OperationFailed


class SiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site: str = Field(min_length=3, max_length=200)


class AccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sites: list[str] = Field(default_factory=list, max_length=50)


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(app: FastAPI, browser: BrowserService) -> None:
    @app.get("/api/browser/sites")
    def list_sites() -> dict[str, Any]:
        return {"available": browser.available, "sites": browser.list_sites()}

    @app.post("/api/browser/sites", status_code=202)
    def connect_site(body: SiteRequest) -> dict[str, Any]:
        try:
            return browser.start_signin(body.site)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.delete("/api/browser/sites/{site}")
    def remove_site(site: str) -> dict[str, Any]:
        try:
            browser.remove_site(site)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {"removed": site}

    @app.get("/api/apps/{app_id}/browser-access")
    def app_access(app_id: str) -> dict[str, Any]:
        allowed = set(browser.grants(app_id))
        return {
            "sites": [
                {"site": s["site"], "state": s["state"], "allowed": s["site"] in allowed}
                for s in browser.list_sites()
            ]
        }

    @app.put("/api/apps/{app_id}/browser-access")
    def set_app_access(app_id: str, body: AccessRequest) -> dict[str, Any]:
        try:
            allowed = set(browser.set_grants(app_id, body.sites))
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {
            "sites": [
                {"site": s["site"], "state": s["state"], "allowed": s["site"] in allowed}
                for s in browser.list_sites()
            ]
        }

    @app.get("/api/apps/{app_id}/browser-visits")
    def app_visits(app_id: str) -> dict[str, Any]:
        return {"visits": browser.visits(app_id)}
