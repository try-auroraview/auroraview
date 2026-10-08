"""Process-group ownership contracts run without sending any real signal."""

from __future__ import annotations

import signal
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from auroraview_offscreen._posix import ProcessGroup  # noqa: E402


class ProcessGroupTests(unittest.TestCase):
    def group(self, records):
        platform = patch("auroraview_offscreen._posix.sys.platform", "linux")
        platform.start()
        self.addCleanup(platform.stop)
        sigkill = patch("auroraview_offscreen._posix.signal.SIGKILL", 9, create=True)
        sigkill.start()
        self.addCleanup(sigkill.stop)
        stat = patch.object(ProcessGroup, "_stat", side_effect=lambda pid: records.get(pid))
        stat.start()
        self.addCleanup(stat.stop)
        entries = patch(
            "auroraview_offscreen._posix.Path.iterdir",
            return_value=[Path("/proc") / str(pid) for pid in records] + [Path("/proc/self")],
        )
        entries.start()
        self.addCleanup(entries.stop)
        return ProcessGroup(123)

    def test_stat_parses_command_with_spaces_and_parentheses(self):
        fields = ["S", "1", "123", "123"] + ["0"] * 15 + ["987"]
        with patch.object(
            Path, "read_text", return_value="123 (render ) process (name) " + " ".join(fields)
        ):
            self.assertEqual(ProcessGroup._stat(123), ("S", 123, 123, 987))
        for text in ("123 broken " + " ".join(fields), "123 (render) S 1 2"):
            with self.subTest(text=text), patch.object(Path, "read_text", return_value=text):
                with self.assertRaisesRegex(ValueError, "Incomplete"):
                    ProcessGroup._stat(123)

    def test_stat_missing_is_distinct_from_access_failure(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertIsNone(ProcessGroup._stat(123))
        with patch.object(Path, "read_text", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                ProcessGroup._stat(123)

    def test_requires_owned_group_and_session(self):
        for identity in (("S", 124, 123, 10), ("S", 123, 124, 10)):
            with (
                self.subTest(identity=identity),
                self.assertRaisesRegex(ValueError, "start_new_session"),
            ):
                self.group({123: identity})

    def test_inventory_requires_both_owned_group_and_session(self):
        group = self.group(
            {
                123: ("S", 123, 123, 10),
                124: ("R", 123, 123, 11),
                125: ("R", 999, 123, 12),
                126: ("R", 123, 999, 13),
            }
        )
        group._capture(float("inf"))
        self.assertEqual(group._members, {(123, 10), (124, 11)})

    def test_missing_startup_leader_never_signals_recycled_group(self):
        records = {123: None}
        group = self.group(records)
        records[123] = ("S", 123, 123, 999)
        with patch("auroraview_offscreen._posix.os.killpg", create=True) as kill:
            group.terminate(float("inf"))
        kill.assert_not_called()
        self.assertTrue(group._retired)

    def test_recycled_leader_permanently_retires_group_identity(self):
        records = {123: ("S", 123, 123, 10)}
        group = self.group(records)
        records[123] = ("S", 123, 123, 999)
        with patch("auroraview_offscreen._posix.os.killpg", create=True) as kill:
            group.terminate(float("inf"))
            records[123] = ("S", 123, 123, 10)
            group.terminate(float("inf"))
        kill.assert_not_called()

    def test_orphaned_member_is_signaled_once_and_waited_until_exit(self):
        records = {123: ("S", 123, 123, 10), 124: ("R", 123, 123, 11)}
        group = self.group(records)
        records[123] = None
        with patch("auroraview_offscreen._posix.os.killpg", create=True) as kill:
            group.terminate(float("inf"))
            group.terminate(float("inf"))
        kill.assert_called_once_with(123, signal.SIGKILL)
        with patch("auroraview_offscreen._posix.time.sleep") as sleep:
            sleep.side_effect = lambda _: records.update({124: ("Z", 123, 123, 11)})
            group.wait(float("inf"))
        sleep.assert_called_once()
        self.assertEqual(group._members, set())
        self.assertTrue(group._retired)

    def test_live_member_timeout_retains_identity_for_retry(self):
        records = {123: ("S", 123, 123, 10), 124: ("R", 123, 123, 11)}
        group = self.group(records)
        group._members = {(124, 11)}
        with (
            patch.object(group, "_capture"),
            patch("auroraview_offscreen._posix.time.perf_counter", return_value=10),
        ):
            with self.assertRaisesRegex(TimeoutError, "still running"):
                group.wait(10)
            self.assertEqual(group._members, {(124, 11)})
            records[124] = ("Z", 123, 123, 11)
            group.wait(10)
        self.assertEqual(group._members, set())

    def test_recycled_member_cannot_satisfy_retained_identity(self):
        records = {123: ("S", 123, 123, 10), 124: ("R", 123, 123, 999)}
        group = self.group(records)
        group._members = {(124, 11)}
        with patch.object(group, "_capture"):
            group.wait(float("inf"))
        self.assertEqual(group._members, set())

    def test_inventory_budget_expires_before_signal_and_can_retry(self):
        group = self.group({123: ("S", 123, 123, 10)})
        with (
            patch("auroraview_offscreen._posix.time.perf_counter", return_value=10),
            patch("auroraview_offscreen._posix.os.killpg", create=True) as kill,
        ):
            with self.assertRaisesRegex(TimeoutError, "inventory"):
                group.terminate(10)
            kill.assert_not_called()
            group.terminate(11)
        kill.assert_called_once_with(123, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
