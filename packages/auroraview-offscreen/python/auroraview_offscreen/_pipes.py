"""Owned Windows stdout pipe with enough capacity for offscreen pixel bursts."""

from __future__ import annotations

import os
from typing import BinaryIO

OUTPUT_BUFFER_SIZE = 1024 * 1024


class OutputPipe:
    """Own both non-inheritable ends until Popen duplicates the child's writer."""

    def __init__(self, size: int = OUTPUT_BUFFER_SIZE):
        if os.name != "nt":
            raise OSError("Explicit output pipe capacity is Windows-only")
        if not 1 <= size <= OUTPUT_BUFFER_SIZE:
            raise ValueError("Output pipe capacity must be within 1 byte and 1 MiB")
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreatePipe.argtypes = [
            ctypes.POINTER(wintypes.HANDLE),
            ctypes.POINTER(wintypes.HANDLE),
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.CreatePipe.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        read_handle, write_handle = wintypes.HANDLE(), wintypes.HANDLE()
        self.reader: BinaryIO | None = None
        self.writer: BinaryIO | None = None
        if not kernel.CreatePipe(ctypes.byref(read_handle), ctypes.byref(write_handle), None, size):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            # open_osfhandle transfers each native handle to its CRT descriptor.
            for handle, flags, mode, attribute in (
                (read_handle, os.O_RDONLY, "rb", "reader"),
                (write_handle, os.O_WRONLY, "wb", "writer"),
            ):
                descriptor = msvcrt.open_osfhandle(handle.value, flags | os.O_BINARY)
                handle.value = None
                try:
                    os.set_inheritable(descriptor, False)
                    stream = os.fdopen(descriptor, mode, buffering=0)
                except BaseException:
                    os.close(descriptor)
                    raise
                setattr(self, attribute, stream)
        except BaseException:
            self.close()
            raise
        finally:
            for handle in (read_handle, write_handle):
                if handle.value is not None:
                    kernel.CloseHandle(handle)

    def take_reader(self) -> BinaryIO:
        """Transfer the parent endpoint to Popen's stdout ownership."""
        if self.reader is None:
            raise RuntimeError("Output pipe reader has already been transferred")
        reader, self.reader = self.reader, None
        return reader

    def close(self) -> None:
        """Close only endpoints which have not been transferred to Popen."""
        for name in ("reader", "writer"):
            stream = getattr(self, name, None)
            if stream is not None:
                stream.close()
                setattr(self, name, None)
