"""How one plan step is judged: with the model made unavailable, either honest outcome passes
(a refusal, or a succeeded run that stored nothing); an invented value or a stored change fails."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from alpha.builds.plan import run_invoke
from alpha_contracts.runs import RunState
from alpha_contracts.verification import CheckStatus, InvokeStep


class Preview:
    timezone = "UTC"

    def __init__(self, state: RunState, stores_after: bool = False) -> None:
        self.models = SimpleNamespace(fault="normal")
        self.app = SimpleNamespace(
            source=SimpleNamespace(collections=[SimpleNamespace(name="leads")])
        )
        self._state = state
        self._stores_after = stores_after
        self._rows: list[Any] = []
        self.faults: list[str] = []

    def records_in(self, name: str) -> list[Any]:
        return list(self._rows)

    def invoke_and_wait(self, action: str, payload: dict[str, Any]) -> Any:
        self.faults.append(self.models.fault)
        if self._stores_after:
            self._rows.append(SimpleNamespace(id="r1", revision=1, values={"n": 1}, provenance={}))
        return SimpleNamespace(
            state=self._state,
            output={"message": "nothing read"},
            run_id="run_1",
            terminal_reason=None,
        )

    def failure_detail(self, run: Any) -> dict[str, Any]:
        return {"error": {"message": "refused"}}


def step() -> InvokeStep:
    return InvokeStep(id="down", action="scan", expect="failed", model="unavailable")


def test_a_succeeded_run_that_stored_nothing_passes_when_the_model_is_unavailable() -> None:
    preview = Preview(RunState.SUCCEEDED)
    result = run_invoke(preview, step(), {}, "behavior.s.down")
    assert result.status is CheckStatus.PASSED
    assert "handled the unavailable model honestly" in result.summary
    assert preview.faults == ["unavailable"] and preview.models.fault == "normal"


def test_a_refusal_still_passes_and_a_stored_change_still_fails() -> None:
    assert run_invoke(Preview(RunState.FAILED), step(), {}, "c").status is CheckStatus.PASSED
    stored = run_invoke(Preview(RunState.SUCCEEDED, stores_after=True), step(), {}, "c")
    assert stored.status is CheckStatus.FAILED
    assert "should have failed" in stored.summary


def test_with_the_model_normal_a_succeeded_run_never_satisfies_expect_failed() -> None:
    normal = InvokeStep(id="bad", action="add", input={}, expect="failed")
    result = run_invoke(Preview(RunState.SUCCEEDED), normal, {}, "c")
    assert result.status is CheckStatus.FAILED
