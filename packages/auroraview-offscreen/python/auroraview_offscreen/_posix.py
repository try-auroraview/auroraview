"""Completion barrier for the isolated renderer's POSIX process group."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path


class ProcessGroup:
    """Signal only the start_new_session group and retain exact Linux identities."""

    def __init__(self, pid: int):
        self.pid = pid
        self._linux = sys.platform.startswith("linux")
        self._members: set[tuple[int, int]] = set()
        self._signaled = False
        self._retired = False
        self._birth: int | None = None
        if self._linux:
            record = self._stat(pid)
            if record is None:
                # The broker cannot spawn children before ProcessTree is made.
                # An already exited startup therefore owns no remaining group.
                self._retired = True
            elif record[1:3] != (pid, pid):
                raise ValueError("Renderer process must own a start_new_session process group")
            else:
                self._birth = record[3]
            return
        try:
            if os.getpgid(pid) != pid or os.getsid(pid) != pid:
                raise ValueError("Renderer process must own a start_new_session process group")
        except ProcessLookupError:
            self._retired = True

    @staticmethod
    def _stat(pid: int) -> tuple[str, int, int, int] | None:
        try:
            # comm may contain spaces or parentheses; fields after its final ')'
            # begin at state (3), including pgrp (5), session (6), starttime (22).
            _, separator, suffix = Path(f"/proc/{pid}/stat").read_text().rpartition(")")
        except (FileNotFoundError, ProcessLookupError):
            return None
        fields = suffix.split()
        if not separator or len(fields) < 20:
            raise ValueError("Incomplete process identity in procfs")
        return fields[0], int(fields[2]), int(fields[3]), int(fields[19])

    def _capture(self, deadline: float) -> None:
        if self._retired:
            return
        leader = self._stat(self.pid)
        if leader is not None and (leader[3] != self._birth or leader[1:3] != (self.pid, self.pid)):
            self._retired = True
            return  # The numeric group leader PID now belongs to another session.
        # Linux exposes no group-member list syscall. Filter procfs strictly by
        # this isolated pgrp AND session; unrelated identities are never retained
        # or signaled. Existing identities keep their original starttime.
        for entry in Path("/proc").iterdir():
            if time.perf_counter() >= deadline:
                raise TimeoutError("Owned renderer process-group inventory exceeded its budget")
            if not entry.name.isdecimal():
                continue
            try:
                record = self._stat(int(entry.name))
            except (OSError, ValueError, IndexError):
                continue  # An unrelated process may disappear or deny stat access.
            if record is not None and record[1:3] == (self.pid, self.pid):
                self._members.add((int(entry.name), record[3]))

    def terminate(self, deadline: float) -> None:
        if self._linux:
            self._capture(deadline)
            leader = self._stat(self.pid)
            if leader is not None and (
                leader[3] != self._birth or leader[1:3] != (self.pid, self.pid)
            ):
                self._retired = True
        if self._retired:
            return  # Never signal a missing or recycled group identifier.
        if not self._signaled:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._signaled = True

    def wait(self, deadline: float) -> None:
        while True:
            if self._linux:
                self._capture(deadline)
                remaining = set()
                for pid, birth in self._members:
                    record = self._stat(pid)
                    # Zombies have exited and hold no pipes; their new parent
                    # owns waitpid. A recycled PID cannot satisfy old ownership.
                    if record is not None and record[3] == birth and record[0] not in {"Z", "X"}:
                        remaining.add((pid, birth))
                self._members = remaining
                if not remaining:
                    self._retired = True
                    return
            else:
                try:
                    os.killpg(self.pid, 0)
                except ProcessLookupError:
                    self._retired = True
                    return
            remaining_time = deadline - time.perf_counter()
            if remaining_time <= 0:
                raise TimeoutError("Owned renderer descendants are still running")
            time.sleep(min(0.001, remaining_time))
