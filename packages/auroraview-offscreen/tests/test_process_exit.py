"""Real owned child exit checks; no native application or global process cleanup."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from auroraview_offscreen import RendererProcess  # noqa: E402
from auroraview_offscreen._job import ProcessTree  # noqa: E402

CHILD = r"""
import json,os,struct,subprocess,sys,time
from pathlib import Path
root=Path(__file__).parent
mode=(root/'mode').read_text()
def stage(value):
    (root/'stage').write_text(value)
stage('entered')
def send(message):
    header=json.dumps(message).encode()
    sys.stdout.buffer.write(struct.pack('<II',len(header),0)+header)
    sys.stdout.buffer.flush()
if mode=='pipe_hang':
    send({'type':'ready','protocol':1})
    while True:time.sleep(1)
if mode=='protocol_failure':
    sys.stdout.buffer.write(struct.pack('<II',0,0));sys.stdout.buffer.flush()
    while True:time.sleep(1)
send({'type':'ready','protocol':1})
stage('ready')
for line in sys.stdin.buffer:
    command=json.loads(line)
    stage('received '+command['type'])
    if command['type']=='create':
        # Spawn after the parent's Job assignment, while retaining inherited pipes.
        descendant=subprocess.Popen([sys.executable,'-c','import time;time.sleep(600)'],
                                    stdin=sys.stdin,stdout=sys.stdout,stderr=sys.stderr,
                                    creationflags=(subprocess.CREATE_NO_WINDOW
                                                   if os.name=='nt' else 0))
        stage('spawned '+str(descendant.pid))
        (root/'descendant').write_text(str(descendant.pid))
        send({'type':'event','surface_id':command['surface_id'],'generation':command['generation'],
              'event':'spawned','detail':descendant.pid})
    if command['type']=='shutdown':break
"""


class ProcessTreeTests(unittest.TestCase):
    def test_timeout_is_explicit_and_retains_retryable_ownership(self):
        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired("owned-child", 0.25)
        # Test the common reap contract without creating an OS Job for a fake PID.
        tree = object.__new__(ProcessTree)
        tree.process, tree._handle = process, None
        with self.assertRaisesRegex(TimeoutError, "250 ms"):
            tree.close()
        self.assertIs(tree.process, process)
        process.wait.side_effect = None
        process.wait.return_value = 0
        tree.close()
        self.assertEqual(process.wait.call_count, 2)


@unittest.skipIf(
    os.name == "nt" and sys.version_info < (3, 12), "Windows pipes require Python3.12+"
)
class ProcessExitTests(unittest.TestCase):
    def make_client(self, mode: str):
        temporary = tempfile.TemporaryDirectory(prefix="auroraview-offscreen-exit-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "main.cjs").write_text("test sentinel", encoding="utf-8")
        (root / "stdio.cjs").write_text(CHILD, encoding="utf-8")
        (root / "mode").write_text(mode, encoding="utf-8")
        # Process creation can exceed a second on a loaded native host; teardown
        # has its own strict 250 ms bound, independent of this handshake allowance.
        client = RendererProcess(
            sys.executable, root, startup_timeout=5, log_path=root / "child.log"
        )
        client._test_root = root

        def cleanup():
            # Failure cleanup is restricted to the exact process tree this test owns.
            deadline = time.perf_counter() + 3
            while not client.closed:
                try:
                    client.terminate()
                except TimeoutError:
                    if time.perf_counter() >= deadline:
                        # Preserve the failure while releasing the test runner's
                        # local pipe/log endpoints; the outer bounded Job owns
                        # final cleanup if the kernel still has an exiting child.
                        for stream in (client._process.stdin, client._process.stdout, client._log):
                            if stream is not None:
                                stream.close()
                        self.fail(
                            f"Owned cleanup failed: pid={client.pid}, "
                            f"job={client._tree._handle}, "
                            f"pending_handles={client._tree._pending_handles}"
                        )
                    time.sleep(0.002)

        self.addCleanup(cleanup)
        return client, root

    def until(self, client, predicate, timeout=6):
        messages = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            messages.extend(client.poll())
            if predicate(messages):
                return messages
            time.sleep(0.002)
        root = client._test_root
        stage = (root / "stage").read_text() if (root / "stage").exists() else "not entered"
        self.fail(
            f"Owned child condition timed out: {messages}, {client.last_error}, "
            f"stage={stage}, pending={client.pending_bytes}, "
            f"stderr={(root / 'child.log').read_text()}"
        )

    def assert_reaped(self, client):
        self.assertTrue(client.closed)
        self.assertIsNotNone(client._process.returncode)
        self.assertIsNotNone(client._process.poll())
        self.assertTrue(client._process.stdin.closed)
        self.assertTrue(client._process.stdout.closed)

    def descendant_handle(self, pid, tree):
        if os.name != "nt":
            return None
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p]
        kernel.IsProcessInJob.restype = wintypes.BOOL
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        handle = kernel.OpenProcess(
            0x101001, False, pid
        )  # Wait, query membership and owned cleanup.
        self.assertTrue(handle, "Owned descendant disappeared before exit observation")

        def cleanup():
            if kernel.WaitForSingleObject(handle, 0) == 258:
                kernel.TerminateProcess(handle, 1)
                kernel.WaitForSingleObject(handle, 1000)
            kernel.CloseHandle(handle)

        self.addCleanup(cleanup)
        owned = wintypes.BOOL()
        self.assertTrue(kernel.IsProcessInJob(handle, tree._handle, ctypes.byref(owned)))
        self.assertTrue(owned.value, f"Descendant {pid} escaped renderer Job")
        return kernel, handle

    def assert_descendant_exited(self, pid, handle):
        if os.name == "nt":
            kernel, process_handle = handle
            self.assertEqual(
                kernel.WaitForSingleObject(process_handle, 0), 0, f"Descendant {pid} remains alive"
            )
        elif Path(f"/proc/{pid}/stat").exists():
            # Reparented zombies have exited; the OS init process owns their reaping.
            self.assertEqual(Path(f"/proc/{pid}/stat").read_text().split()[2], "Z")
        else:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_normal_shutdown_reaps_parent_and_inherited_pipe_child(self):
        client, _ = self.make_client("normal")
        client.create("owned", 1, 2, 1, html="test")
        messages = self.until(
            client, lambda items: any(item.get("event") == "spawned" for item in items)
        )
        descendant = next(item["detail"] for item in messages if item.get("event") == "spawned")
        handle = self.descendant_handle(descendant, client._tree)
        started = time.monotonic()
        client.shutdown()
        self.until(client, lambda _: client.closed)
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertEqual(client._process.returncode, 0)
        self.assert_reaped(client)
        self.assert_descendant_exited(descendant, handle)

    def test_protocol_failure_reaps_before_returning_error(self):
        client, _ = self.make_client("protocol_failure")
        self.until(client, lambda items: any(item["type"] == "error" for item in items))
        self.assert_reaped(client)

    def test_cancel_repeated_launches_reaps_and_closes_pipes(self):
        for attempt in range(4):
            with self.subTest(attempt=attempt):
                client, _ = self.make_client("pipe_hang")
                self.until(client, lambda _, owned=client: owned.ready)
                started = time.monotonic()
                client.terminate()
                self.assertLess(time.monotonic() - started, 0.35)
                self.assert_reaped(client)
                client.terminate()

    def test_full_outbound_pipe_cannot_block_cancel(self):
        client, _ = self.make_client("pipe_hang")
        self.until(client, lambda _: client.ready)
        client.create("owned", 1, 2, 1, html="x" * 800000)
        started = time.monotonic()
        client.poll()
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertGreater(client.pending_bytes, 0)
        client.terminate()
        self.assert_reaped(client)

    def test_destructor_reaps_without_resource_warning(self):
        client, _ = self.make_client("pipe_hang")
        self.until(client, lambda _: client.ready)
        process = client._process
        # Exercise destruction directly, retaining Popen so its returncode is observable.
        client.__del__()
        self.assertIsNotNone(process.returncode)
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter("always", ResourceWarning)
            process.__del__()
        self.assertFalse([item for item in observed if issubclass(item.category, ResourceWarning)])

    def test_cleanup_timeout_reports_pending_and_retries_once_per_tick(self):
        client, _ = self.make_client("pipe_hang")
        self.until(client, lambda _: client.ready)
        original_close = client._tree.close
        attempts = 0

        def delayed_close(*, force):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("Owned test process is still exiting")
            original_close(force=force)

        with patch.object(client._tree, "close", side_effect=delayed_close):
            client.shutdown()
            client._shutdown_at = 0
            first = client.poll()
            self.assertEqual(attempts, 1)
            self.assertFalse(client.closed)
            self.assertEqual([item["code"] for item in first], ["cleanup_pending"])
            self.assertFalse(client._process.stdin.closed)
            self.until(client, lambda _: client.closed)
            self.assertGreaterEqual(attempts, 2)
        self.assert_reaped(client)

    def test_failed_transport_cleanup_rejects_new_commands_and_retries(self):
        client, _ = self.make_client("protocol_failure")
        original_close = client._tree.close
        attempts = 0

        def delayed_close(*, force):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("Owned test process is still exiting")
            original_close(force=force)

        with patch.object(client._tree, "close", side_effect=delayed_close):
            messages = self.until(
                client,
                lambda items: any(item.get("code") == "renderer_disconnected" for item in items),
            )
            self.assertEqual(attempts, 1)
            self.assertFalse(client.closed)
            self.assertTrue(any(item.get("code") == "cleanup_pending" for item in messages))
            with self.assertRaisesRegex(RuntimeError, "connection is closed"):
                client.create("late", 1, 1, 1, html="late")
            self.until(client, lambda _: client.closed)
        self.assert_reaped(client)


if __name__ == "__main__":
    unittest.main()
