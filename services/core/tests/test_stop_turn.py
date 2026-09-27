"""A turn that is taking long can be stopped: the CLI process is killed and the conversation
says plainly that the person stopped it."""

from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

import pytest
from alpha.models.gateway import ModelGateway
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore


def slow_cli(tmp_path: Path) -> Path:
    script = tmp_path / "claude"
    script.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_a_running_call_can_be_stopped(tmp_path: Path) -> None:
    gateway = ModelGateway(
        ControlStore(tmp_path / "control.sqlite"), frozenset({"claude-code-cli"})
    )
    inference = StructuredInference(
        gateway, claude_binary=str(slow_cli(tmp_path)), timeout_seconds=60
    )
    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            inference.call(
                gateway.route("claude-code-cli"),
                system="s",
                prompt="p",
                schema={"type": "object", "properties": {}},
                scope_kind="assistant_turn",
                scope_ref="conv_1",
            )
        except InferenceError as exc:
            outcome["code"] = exc.code

    thread = threading.Thread(target=run)
    started = time.monotonic()
    thread.start()
    deadline = time.monotonic() + 5
    while not inference.cancel("conv_1") and time.monotonic() < deadline:
        time.sleep(0.05)
    thread.join(timeout=10)
    assert outcome == {"code": "cancelled"}
    assert time.monotonic() - started < 10, "stopping did not wait for the 30 s process"
    assert inference.cancel("conv_1") is False, "nothing left running"


@pytest.mark.skipif(os.name != "posix", reason="shell script fixture")
def test_stopping_nothing_is_a_plain_no(tmp_path: Path) -> None:
    gateway = ModelGateway(ControlStore(tmp_path / "control.sqlite"), frozenset({"fake"}))
    assert StructuredInference(gateway).cancel("conv_none") is False
