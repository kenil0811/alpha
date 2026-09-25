"""Exclusive data-directory lock. One Core per data directory: a second runtime on the same
directory would reconcile the first one's live workers as orphans and race its writes."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


class DataDirectoryBusy(RuntimeError):
    def __init__(self, path: Path, holder: str) -> None:
        super().__init__(
            f"another Alpha runtime is already using this data directory ({path.parent}); "
            f"holder pid {holder or 'unknown'}"
        )
        self.holder = holder


class DataDirectoryLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = os.read(fd, 64).decode("utf-8", "replace").strip()
            os.close(fd)
            raise DataDirectoryBusy(self._path, holder) from None
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
