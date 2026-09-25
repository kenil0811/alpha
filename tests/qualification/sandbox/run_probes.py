"""F03.C03 sandbox feasibility probes on the pinned sandbox-runtime candidate (macOS seatbelt).

Builds a synthetic world (canary secret, a fake data directory, private scratch, a loopback
listener), writes a restrictive srt settings file, runs probe_payload.py under `srt`, and
compares observations with the expectations of the App/Task worker profile. The report records
every probe including failures and the resulting F20 gap list. It never claims containment.

Usage: uv run python tests/qualification/sandbox/run_probes.py [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRT = REPO_ROOT / "tests/qualification/sandbox/node_modules/.bin/srt"
PAYLOAD = Path(__file__).with_name("probe_payload.py")
# srt itself is a Node CLI; the sandboxed command uses absolute paths only.
TOOL_PATH = "/opt/homebrew/opt/node@24/bin:/usr/bin:/bin"

# Expectation for the App/Task worker profile (Deployment and Execution Architecture):
# immutable code, scoped broker only, temporary files, no ambient network/home.
EXPECT: dict[str, bool | None] = {
    "read_canary": False,
    "read_etc_passwd": None,  # documented default: unrestricted reads; recorded, not judged
    "write_scratch": True,
    "write_outside": False,
    "symlink_escape": False,
    "subprocess_cat_canary": False,  # child inherits the sandbox: must not read the canary
    "subprocess_sh": None,  # allowed to spawn; recorded
    "tcp_public": False,
    "http_public": False,
    "tcp_loopback": False,  # broker access must be explicit; ambient loopback is a gap
    "listen_socket": False,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if not SRT.exists():
        print(f"srt not installed at {SRT}; run pnpm install", file=sys.stderr)
        return 2
    version = subprocess.run(
        [str(SRT), "--version"], capture_output=True, text=True, env={"PATH": TOOL_PATH}
    ).stdout.strip()

    world = Path(tempfile.mkdtemp(prefix="alpha-sandbox-world-"))
    home = world / "home"
    data = world / "data"
    scratch = world / "scratch"
    for d in (home, data, scratch):
        d.mkdir()
    canary = home / ".alpha-canary-secret"
    canary.write_text("CANARY-SECRET-DO-NOT-READ\n", encoding="utf-8")
    (data / "control.sqlite").write_bytes(b"fake-control-store")
    outside = world / "outside-write.txt"

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port = listener.getsockname()[1]
    accepted: list[str] = []

    def serve() -> None:
        listener.settimeout(20)
        try:
            while True:
                conn, _ = listener.accept()
                accepted.append("connection")
                conn.close()
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()

    settings = {
        "network": {"allowedDomains": [], "deniedDomains": [], "allowLocalBinding": False},
        "filesystem": {
            "denyRead": [str(home), str(data)],
            "allowRead": [],
            "allowWrite": [str(scratch)],
            "denyWrite": [],
        },
        "enableWeakerNestedSandbox": False,
        "enableWeakerNetworkIsolation": False,
        "allowAppleEvents": False,
    }
    settings_path = world / "srt-settings.json"
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    spec = {
        "canary": str(canary),
        "scratch": str(scratch),
        "outside_write": str(outside),
        "loopback_port": port,
    }
    spec_path = world / "probe-spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    # srt takes the command as separate arguments; no shell quoting is involved.
    command = [sys.executable, "-I", "-B", str(PAYLOAD), str(spec_path)]
    # srt creates Unix sockets under TMPDIR; macOS caps socket paths at ~104 bytes.
    srt_tmp = Path(f"/tmp/alpha-srt-{os.getpid()}")
    srt_tmp.mkdir(exist_ok=True)
    started = datetime.now(UTC)
    proc = subprocess.run(
        [str(SRT), "--settings", str(settings_path), *command],
        cwd=str(scratch),
        capture_output=True,
        text=True,
        timeout=120,
        env={
            "PATH": TOOL_PATH,
            "HOME": str(home),
            "USER": os.environ.get("USER", "alpha"),
            "TMPDIR": str(srt_tmp),
        },
    )
    observed: dict[str, dict[str, object]] = {}
    for line in proc.stdout.splitlines():
        if line.startswith("{"):
            try:
                observed = json.loads(line)
            except json.JSONDecodeError:
                pass
    probes: list[dict[str, object]] = []
    gaps: list[dict[str, object]] = []
    for name, expect in EXPECT.items():
        obs = observed.get(name)
        if obs is None:
            probes.append(
                {
                    "probe": name,
                    "expected_allowed": expect,
                    "observed": "no result",
                    "verdict": "no_result",
                }
            )
            continue
        allowed = bool(obs.get("ok"))
        if expect is None:
            verdict = "recorded"
        elif allowed == expect:
            verdict = "pass"
        else:
            verdict = "FAIL"
            gaps.append({"probe": name, "expected_allowed": expect, "observed": obs})
        probes.append(
            {"probe": name, "expected_allowed": expect, "observed": obs, "verdict": verdict}
        )
    cleanup_ok = True
    try:
        shutil.rmtree(scratch)
        cleanup_ok = not scratch.exists()
    except OSError:
        cleanup_ok = False
    report = {
        "candidate": {
            "package": "@anthropic-ai/sandbox-runtime",
            "version": version,
            "enforcement": "macOS sandbox-exec (seatbelt) + srt proxies",
        },
        "started_at": started.isoformat(),
        "host": {"platform": sys.platform, "python": sys.version.split()[0]},
        "settings": settings,
        "srt_exit_code": proc.returncode,
        "srt_stderr_tail": proc.stderr[-1500:],
        "probes": probes,
        "loopback_listener_accepted": accepted,
        "cleanup_scratch_removed": cleanup_ok,
        "gaps_for_F20": gaps,
        "world": str(world),
    }
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    out = args.out or (REPO_ROOT / "docs/development/evidence/logs" / f"F03-sandbox-{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for p in probes:
        print(
            f"  {str(p['verdict']):<9} {str(p['probe']):<24} "
            f"expected_allowed={p['expected_allowed']} observed={json.dumps(p['observed'])[:90]}"
        )
    print(
        f"srt exit {proc.returncode}; loopback connections seen: {len(accepted)}; "
        f"scratch cleaned: {cleanup_ok}"
    )
    print(f"gaps for F20: {len(gaps)}; report: {out}")
    shutil.rmtree(world, ignore_errors=True)
    shutil.rmtree(srt_tmp, ignore_errors=True)
    return 0 if not any(p["verdict"] == "no_result" for p in probes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
