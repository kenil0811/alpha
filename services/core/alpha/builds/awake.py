"""Keep the Mac awake while a build runs.

Attempt deadlines use monotonic timers, which stop while the Mac sleeps: a laptop that idles
into sleep mid-build freezes the build for hours (found in F07's live qualification). While a
build runs, an idle-sleep assertion is held with macOS's own `caffeinate -i`, tied to Core's
process so it can never outlive Core. Closing the lid still sleeps the Mac; the build then
resumes or times out when it wakes.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

CAFFEINATE = Path("/usr/bin/caffeinate")


@contextmanager
def stay_awake() -> Iterator[bool]:
    """Hold an idle-sleep assertion for the duration of the block (no-op where unavailable)."""
    if not CAFFEINATE.is_file():
        yield False
        return
    process = subprocess.Popen(
        [str(CAFFEINATE), "-i", "-w", str(os.getpid())],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield True
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
