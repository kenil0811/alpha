"""Runs INSIDE the sandbox candidate. Every probe reports what it observed; nothing here is
trusted to be correct — the runner outside compares observations with expectations."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.request
from collections.abc import Callable


def attempt(fn: Callable[[], object]) -> dict[str, object]:
    try:
        return {"ok": True, "value": fn()}
    except BaseException as exc:  # noqa: BLE001 - we want every failure class recorded
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}


def child_reads_canary(canary: str) -> str:
    """Only a child that actually printed the canary counts as a read."""
    proc = subprocess.run(["/bin/cat", canary], capture_output=True, text=True, timeout=5)
    if proc.returncode != 0 or "CANARY" not in proc.stdout:
        raise PermissionError(
            f"child denied: rc={proc.returncode} stderr={proc.stderr.strip()[:120]}"
        )
    return proc.stdout[:20]


def read_via_symlink(canary: str, scratch: str) -> str:
    link = os.path.join(scratch, "link")
    os.symlink(canary, link)
    with open(link, encoding="utf-8") as handle:
        return handle.read()[:20]


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as handle:
        spec = json.load(handle)
    canary = spec["canary"]
    scratch = spec["scratch"]
    outside = spec["outside_write"]
    loopback_port = int(spec["loopback_port"])
    results = {
        "read_canary": attempt(lambda: open(canary, encoding="utf-8").read()[:20]),
        "read_etc_passwd": attempt(lambda: open("/etc/passwd", encoding="utf-8").read()[:10]),
        "write_scratch": attempt(
            lambda: open(os.path.join(scratch, "ok.txt"), "w", encoding="utf-8").write("x")
        ),
        "write_outside": attempt(lambda: open(outside, "w", encoding="utf-8").write("x")),
        "symlink_escape": attempt(lambda: read_via_symlink(canary, scratch)),
        "subprocess_cat_canary": attempt(lambda: child_reads_canary(canary)),
        "subprocess_sh": attempt(
            lambda: subprocess.run(
                ["/bin/sh", "-c", "echo shell-ok"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
        ),
        "tcp_public": attempt(
            lambda: socket.create_connection(("1.1.1.1", 443), timeout=4).close()
        ),
        "http_public": attempt(
            lambda: urllib.request.urlopen("https://example.com/", timeout=6).status
        ),
        "tcp_loopback": attempt(
            lambda: socket.create_connection(("127.0.0.1", loopback_port), timeout=3).close()
        ),
        "listen_socket": attempt(lambda: socket.socket().bind(("127.0.0.1", 0))),
        "env_keys": attempt(
            lambda: sorted(k for k in os.environ if k in ("HOME", "PATH", "USER", "TMPDIR"))
        ),
        "cwd": attempt(os.getcwd),
    }
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
