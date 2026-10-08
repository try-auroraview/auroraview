"""Own only this renderer process tree; never enumerate unrelated processes."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time

from ._posix import ProcessGroup

EXIT_TIMEOUT = 0.25


class ProcessTree:
    def __init__(self, process) -> None:
        self.process = process
        self._handle = None
        self._pending_handles = []
        self._pending_ids = set()
        self._group = None
        if os.name != "nt":
            self._group = ProcessGroup(process.pid)
            return
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IOStats(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IOStats),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class Accounting(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_int64),
                ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p]
        kernel.IsProcessInJob.restype = wintypes.BOOL
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        try:
            if not kernel.SetInformationJobObject(
                handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        self._kernel, self._handle, self._accounting_type = kernel, handle, Accounting

    def _capture_handles(self, deadline: float) -> None:
        """Retain waitable handles for this Job's members, without global PID scans."""
        from ctypes import wintypes

        capacity = 16
        while capacity <= 4096:
            if time.perf_counter() >= deadline:
                raise TimeoutError("Owned renderer Job inventory exceeded its budget")
            buffer = ctypes.create_string_buffer(8 + ctypes.sizeof(ctypes.c_size_t) * capacity)
            if self._kernel.QueryInformationJobObject(
                self._handle,
                3,
                buffer,
                ctypes.sizeof(buffer),
                None,
            ):
                count = wintypes.DWORD.from_buffer(buffer, 4).value
                ids = (ctypes.c_size_t * count).from_buffer(buffer, 8)
                for pid in ids:
                    if time.perf_counter() >= deadline:
                        raise TimeoutError("Owned renderer Job inventory exceeded its budget")
                    if pid in self._pending_ids:
                        continue
                    # Job membership may change between the snapshot and OpenProcess.
                    handle = self._kernel.OpenProcess(0x101000, False, pid)
                    if not handle:
                        if ctypes.get_last_error() == 87:  # Process already exited.
                            continue
                        raise ctypes.WinError(ctypes.get_last_error())
                    owned = wintypes.BOOL()
                    if not self._kernel.IsProcessInJob(handle, self._handle, ctypes.byref(owned)):
                        self._kernel.CloseHandle(handle)
                        raise ctypes.WinError(ctypes.get_last_error())
                    if owned.value:
                        self._pending_handles.append(handle)
                        self._pending_ids.add(pid)
                    else:
                        self._kernel.CloseHandle(handle)
                return
            if ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                raise ctypes.WinError(ctypes.get_last_error())
            capacity *= 2
        raise RuntimeError("Owned renderer Job exceeds the process inventory limit")

    def close(self, *, force: bool = False, timeout: float = EXIT_TIMEOUT) -> None:
        """Stop and reap the owned tree within one bounded, retryable deadline.

        Closing a kill-on-close Job is asynchronous. Terminate it explicitly and
        keep its handle until both Popen and the Job's descendants have exited.
        Only explicit teardown waits; transport polling never calls this until
        shutdown, failure or cancellation.
        """
        if not 0 < timeout <= 3:
            raise ValueError("Renderer teardown timeout must be within (0, 3] seconds")
        deadline = time.perf_counter() + timeout
        if self._handle is not None:
            self._capture_handles(deadline)
            if not self._kernel.TerminateJobObject(self._handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
        elif force and getattr(self, "_group", None) is not None:
            self._group.terminate(deadline)
        elif force and self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=max(0.0, deadline - time.perf_counter()))
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Owned renderer process did not exit within {timeout * 1000:g} ms"
            ) from exc
        if getattr(self, "_group", None) is not None:
            self._group.wait(deadline)
        if self._handle is not None:
            accounting = self._accounting_type()
            while True:
                if not self._kernel.QueryInformationJobObject(
                    self._handle,
                    1,
                    ctypes.byref(accounting),
                    ctypes.sizeof(accounting),
                    None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if accounting.ActiveProcesses == 0:
                    break
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Owned renderer descendants did not exit within {timeout * 1000:g} ms"
                    )
                time.sleep(min(0.001, remaining))
            # Accounting can reach zero before a terminating process handle signals.
            # Wait those exact owned handles before claiming the tree has exited.
            for handle in self._pending_handles:
                milliseconds = max(0, int((deadline - time.perf_counter()) * 1000))
                result = self._kernel.WaitForSingleObject(handle, milliseconds)
                if result == 258:
                    raise TimeoutError(
                        f"Owned renderer descendants did not exit within {timeout * 1000:g} ms"
                    )
                if result != 0:
                    raise ctypes.WinError(ctypes.get_last_error())
            for handle in self._pending_handles:
                self._kernel.CloseHandle(handle)
            self._pending_handles.clear()
            self._pending_ids.clear()
            if not self._kernel.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None
