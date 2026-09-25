"""Synthetic worker profile (F01 transport fixture).

Reads one JSON payload from stdin, emits JSON lines on stdout and exits. It proves supervision,
event streaming, failure, cancellation and descendant cleanup. It is not app generation.

Payload fields:
  text            str   echoed back (default "")
  steps           int   progress steps to emit (default 3)
  delay_seconds   float pause between steps (default 0.05)
  mode            "succeed" | "fail" | "hang" | "crash" | "exit_without_result"
  spawn_child     bool  start a long-lived child process and report its pid
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> int:
    raw = sys.stdin.readline()
    try:
        payload: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        emit({"kind": "error", "message": f"invalid payload: {exc}"})
        return 2
    text = str(payload.get("text", ""))
    steps = int(payload.get("steps", 3))
    delay = float(payload.get("delay_seconds", 0.05))
    mode = str(payload.get("mode", "succeed"))
    child: subprocess.Popen[bytes] | None = None

    emit({"kind": "progress", "stage": "started", "pid": os.getpid(), "cwd": os.getcwd()})
    if payload.get("spawn_child"):
        child = subprocess.Popen(
            ["/bin/sleep", "600"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        emit({"kind": "progress", "stage": "child_spawned", "child_pid": child.pid})

    for index in range(1, steps + 1):
        time.sleep(delay)
        emit({"kind": "progress", "stage": "step", "step": index, "of": steps})

    if mode == "hang":
        emit({"kind": "progress", "stage": "hanging"})
        while True:
            time.sleep(1)
    if mode == "crash":
        os._exit(9)
    if mode == "fail":
        emit({"kind": "error", "message": "synthetic failure requested", "code": "synthetic_fail"})
        return 3
    if mode == "exit_without_result":
        return 0

    words = [w for w in text.split() if w]
    emit(
        {
            "kind": "result",
            "output": {
                "echo": text,
                "upper": text.upper(),
                "characters": len(text),
                "words": len(words),
                "steps_completed": steps,
                "child_pid": child.pid if child else None,
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
