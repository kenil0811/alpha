"""The person's profile: the facts Alpha knows, where each came from, and the person's say over
every one of them (About you)."""

from __future__ import annotations

from typing import Any

from alpha_contracts.profile import FactClaim, ProfileFact, ProfileView
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.context.onboarding import OnboardingService
from alpha.context.profile import ProfileService
from alpha.context.review import ReviewService


class OnboardingAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str] = Field(default_factory=dict, max_length=8)


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(
    app: FastAPI,
    profile: ProfileService,
    onboarding: OnboardingService | None = None,
    review: ReviewService | None = None,
) -> None:
    if onboarding is not None:
        register_onboarding(app, onboarding)
    if review is not None:
        register_review(app, review)

    @app.get("/api/profile", response_model=ProfileView)
    def get_profile(scope: str = Query(default="person", max_length=80)) -> ProfileView:
        """The person's facts, or (scope=project:<id>) the ones that hold in one project."""
        return profile.view(scope)

    @app.get("/api/profile/history")
    def fact_history(field: str = Query(min_length=1, max_length=64)) -> dict[str, Any]:
        return {"facts": profile.history(field)}

    @app.post("/api/profile/facts", response_model=ProfileFact, status_code=201)
    def add_fact(
        body: FactClaim, scope: str = Query(default="person", max_length=80)
    ) -> ProfileFact:
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
                scope=scope,
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


def register_onboarding(app: FastAPI, onboarding: OnboardingService) -> None:
    @app.get("/api/onboarding")
    def onboarding_status() -> dict[str, Any]:
        return onboarding.status()

    @app.post("/api/onboarding")
    def onboarding_answer(body: OnboardingAnswers) -> dict[str, Any]:
        try:
            return onboarding.answer(body.answers)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/onboarding/skip")
    def onboarding_skip() -> dict[str, Any]:
        return onboarding.skip()


def register_review(app: FastAPI, review: ReviewService) -> None:
    @app.get("/api/nudges")
    def nudges() -> dict[str, Any]:
        last = review.last_run()
        return {"nudges": review.nudges(), "last_run": last.isoformat() if last else None}

    @app.post("/api/nudges/review")
    def review_now() -> dict[str, Any]:
        return {"nudges": review.run()}

    @app.post("/api/nudges/{nudge_id}/dismiss")
    def dismiss(nudge_id: str) -> dict[str, str]:
        review.dismiss(nudge_id)
        return {"nudge_id": nudge_id, "state": "dismissed"}
