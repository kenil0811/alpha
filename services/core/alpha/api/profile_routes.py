"""The person's profile: the facts Alpha knows, where each came from, and the person's say over
every one of them (About you)."""

from __future__ import annotations

from typing import Any

from alpha_contracts.profile import FactClaim, ProfileFact, ProfileView
from fastapi import FastAPI, HTTPException, Query

from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.context.profile import ProfileService


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(app: FastAPI, profile: ProfileService) -> None:
    @app.get("/api/profile", response_model=ProfileView)
    def get_profile() -> ProfileView:
        return profile.view()

    @app.get("/api/profile/history")
    def fact_history(field: str = Query(min_length=1, max_length=64)) -> dict[str, Any]:
        return {"facts": profile.history(field)}

    @app.post("/api/profile/facts", response_model=ProfileFact, status_code=201)
    def add_fact(body: FactClaim) -> ProfileFact:
        """The person states a fact (or corrects one): accepted at once, superseding the old."""
        try:
            return profile.claim(
                body.field,
                body.value,
                provenance="person",
                source="person",
                why=body.why,
                confidence=1.0,
                accepted=True,
            )
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/profile/facts/{fact_id}/accept", response_model=ProfileFact)
    def accept_fact(fact_id: str) -> ProfileFact:
        try:
            return profile.accept(fact_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/profile/facts/{fact_id}/reject")
    def reject_fact(fact_id: str) -> dict[str, str]:
        try:
            profile.reject(fact_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {"fact_id": fact_id, "state": "rejected"}

    @app.post("/api/profile/facts/{fact_id}/forget")
    def forget_fact(fact_id: str) -> dict[str, str]:
        try:
            profile.forget(fact_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {"fact_id": fact_id, "state": "retracted"}
