"""Skills: the abilities Alpha keeps outside any module; listed, edited and run from the shell."""

from __future__ import annotations

from typing import Any

from alpha_contracts.skills import SkillDraft, SkillRun, SkillSpec
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.context.skills import SkillService


class SkillInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, Any] = Field(default_factory=dict, max_length=16)


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(app: FastAPI, skills: SkillService) -> None:
    @app.get("/api/skills")
    def list_skills() -> dict[str, Any]:
        return {"skills": [s.model_dump(mode="json") for s in skills.active()]}

    @app.post("/api/skills", response_model=SkillSpec, status_code=201)
    def create_skill(body: SkillDraft) -> SkillSpec:
        try:
            return skills.create(body, created_by="person")
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.get("/api/skills/{skill_id}")
    def get_skill(skill_id: str) -> dict[str, Any]:
        try:
            spec = skills.get(skill_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {
            "skill": spec.model_dump(mode="json"),
            "runs": [r.model_dump(mode="json") for r in skills.runs(skill_id)],
        }

    @app.put("/api/skills/{skill_id}", response_model=SkillSpec)
    def update_skill(skill_id: str, body: SkillDraft) -> SkillSpec:
        try:
            return skills.update(skill_id, body)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.delete("/api/skills/{skill_id}")
    def retire_skill(skill_id: str) -> dict[str, str]:
        try:
            skills.retire(skill_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {"status": "retired"}

    @app.post("/api/skills/{skill_id}/run", response_model=SkillRun)
    def run_skill(skill_id: str, body: SkillInputs) -> SkillRun:
        # A plain def: FastAPI runs it on a worker thread, so the bounded run never blocks the loop.
        try:
            return skills.run(skill_id, body.inputs)
        except OperationFailed as exc:
            raise _fail(exc) from exc
