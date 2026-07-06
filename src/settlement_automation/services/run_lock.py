from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType


if os.name == "nt":
    import msvcrt
else:
    import fcntl


class RunLock:
    """
    Cross-platform file lock for preventing overlapping daily pipeline runs.

    Protects:
    - Windows Task Scheduler vs manual command
    - Task Scheduler vs future UI-triggered run
    - Manual command vs future UI-triggered run

    On Windows, uses msvcrt.locking.
    On Unix/macOS, uses fcntl.flock.
    """

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._file = None

    def __enter__(self) -> "RunLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Keep the file handle open for the lifetime of the lock.
        self._file = self.lock_path.open("a+", encoding="utf-8")

        # Ensure at least one byte exists for Windows byte-range locking.
        self._file.seek(0)
        content = self._file.read(1)
        if not content:
            self._file.seek(0)
            self._file.write("0")
            self._file.flush()

        try:
            if os.name == "nt":
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        except OSError as exc:
            self._close_file()
            raise RuntimeError(
                f"Another daily pipeline run is already in progress. "
                f"Lock file: {self.lock_path}"
            ) from exc

        self._file.seek(0)
        self._file.truncate()
        self._file.write(f"locked by pid={os.getpid()}\n")
        self._file.flush()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is None:
            return

        try:
            if os.name == "nt":
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._close_file()

    def _close_file(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None