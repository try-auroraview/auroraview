"""Windows pipe capacity, nonblocking reads and constructor resource ownership."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from auroraview_offscreen import RendererProcess  # noqa: E402
from auroraview_offscreen._pipes import OUTPUT_BUFFER_SIZE, OutputPipe  # noqa: E402


@unittest.skipUnless(os.name == "nt" and sys.version_info >= (3, 12), "Windows Python 3.12+")
class OutputPipeTests(unittest.TestCase):
    def test_capacity_and_transfer_keep_empty_reads_nonblocking(self):
        import msvcrt
        from ctypes import wintypes

        pipe = OutputPipe()
        self.addCleanup(pipe.close)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetNamedPipeInfo.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.DWORD)] * 4
        kernel.GetNamedPipeInfo.restype = wintypes.BOOL
        capacity = wintypes.DWORD()
        self.assertTrue(
            kernel.GetNamedPipeInfo(
                msvcrt.get_osfhandle(pipe.reader.fileno()), None, ctypes.byref(capacity), None, None
            )
        )
        self.assertGreaterEqual(capacity.value, OUTPUT_BUFFER_SIZE)
        self.assertFalse(os.get_inheritable(pipe.reader.fileno()))
        self.assertFalse(os.get_inheritable(pipe.writer.fileno()))
        reader = pipe.take_reader()
        self.addCleanup(reader.close)
        os.set_blocking(reader.fileno(), False)
        started = time.monotonic()
        with self.assertRaises(BlockingIOError):
            os.read(reader.fileno(), 1)
        self.assertLess(time.monotonic() - started, 0.05)
        writer = pipe.writer
        pipe.close()
        self.assertTrue(writer.closed)
        self.assertFalse(reader.closed)
        self.assertEqual(os.read(reader.fileno(), 1), b"")

    def test_partial_descriptor_construction_closes_native_and_crt_handles(self):
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessHandleCount.restype = wintypes.BOOL

        def handle_count():
            count = wintypes.DWORD()
            self.assertTrue(
                kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count))
            )
            return count.value

        # Warm imports and native bindings before comparing repeated failures.
        OutputPipe().close()
        baseline = handle_count()
        for _ in range(20):
            with patch("auroraview_offscreen._pipes.os.fdopen", side_effect=OSError("fdopen")):
                with self.assertRaisesRegex(OSError, "fdopen"):
                    OutputPipe()
        self.assertEqual(handle_count(), baseline)

    def test_spawn_failure_closes_both_parent_pipe_ends_and_log(self):
        with tempfile.TemporaryDirectory(prefix="auroraview-offscreen-pipe-") as temporary:
            root = Path(temporary)
            for name in ("main.cjs", "stdio.cjs"):
                (root / name).write_text("pass", encoding="utf-8")
            pipe = OutputPipe()
            reader, writer = pipe.reader, pipe.writer
            with (
                patch("auroraview_offscreen.process.OutputPipe", return_value=pipe),
                patch(
                    "auroraview_offscreen.process.subprocess.Popen", side_effect=OSError("spawn")
                ),
            ):
                with self.assertRaisesRegex(OSError, "spawn"):
                    RendererProcess(sys.executable, root, log_path=root / "renderer.log")
            self.assertTrue(reader.closed)
            self.assertTrue(writer.closed)
            (root / "renderer.log").unlink()  # Windows refuses deletion while the log is open.

    def test_post_spawn_failure_reaps_exact_owned_child_and_closes_descriptors(self):
        with tempfile.TemporaryDirectory(prefix="auroraview-offscreen-pipe-") as temporary:
            root = Path(temporary)
            (root / "main.cjs").write_text("# sentinel", encoding="utf-8")
            (root / "stdio.cjs").write_text("import time; time.sleep(600)", encoding="utf-8")
            children = []
            original = subprocess.Popen

            def spawn(*args, **kwargs):
                child = original(*args, **kwargs)
                children.append(child)
                return child

            with (
                patch("auroraview_offscreen.process.subprocess.Popen", side_effect=spawn),
                patch(
                    "auroraview_offscreen.process.os.set_blocking",
                    side_effect=OSError("nonblocking"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "nonblocking"):
                    RendererProcess(sys.executable, root, log_path=root / "renderer.log")
            self.assertEqual(len(children), 1)
            child = children[0]
            self.assertIsNotNone(child.returncode)
            self.assertTrue(child.stdin.closed)
            self.assertTrue(child.stdout.closed)
            (root / "renderer.log").unlink()


if __name__ == "__main__":
    unittest.main()
