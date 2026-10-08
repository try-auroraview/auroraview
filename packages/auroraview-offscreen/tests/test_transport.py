"""Private transport contracts, using an owned child and no desktop automation."""

import json
import os
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from auroraview_offscreen import FrameDecoder, ProtocolError, RendererProcess  # noqa: E402
from auroraview_offscreen.protocol import encode_command  # noqa: E402


def envelope(header, payload=b""):
    data = json.dumps(header).encode()
    return struct.pack("<II", len(data), len(payload)) + data + payload


def frame(**overrides):
    return {
        "type": "frame",
        "surface_id": "one",
        "generation": 1,
        "seq": 1,
        "width": 2,
        "height": 1,
        "stride": 8,
        "format": "rgba8",
        "alpha": "straight",
        "origin": "top-left",
        "resize_revision": 0,
        **overrides,
    }


class DecoderTests(unittest.TestCase):
    def test_fragmented_binary_frame_with_following_control(self):
        decoder = FrameDecoder()
        data = envelope(frame(), b"\x00\x0a\x0d\xff" * 2) + envelope(
            {"type": "ready", "protocol": 1}
        )
        output = []
        for byte in data:
            output.extend(decoder.feed(bytes([byte])))
        self.assertEqual(output[0]["payload"], b"\x00\x0a\x0d\xff" * 2)
        self.assertEqual(output[1], {"type": "ready", "protocol": 1})
        self.assertEqual(decoder.pending, 0)

    def test_peer_lengths_rejected_before_allocation(self):
        for header_size, payload_size in ((0, 0), (65537, 0), (1, 67108865)):
            with self.subTest(header_size=header_size, payload_size=payload_size):
                with self.assertRaises(ProtocolError):
                    FrameDecoder().feed(struct.pack("<II", header_size, payload_size))

    def test_bad_pixels_and_json_fail_closed(self):
        for data in (
            envelope(frame(width=True), b"1234"),
            envelope(frame(), b"1234"),
            envelope(frame(format="bgra8"), b"12345678"),
            envelope({"type": "ready"}, b"unexpected"),
            struct.pack("<II", 1, 0) + b"!",
        ):
            with self.subTest(data=data[:40]), self.assertRaises(ProtocolError):
                FrameDecoder().feed(data)

    def test_finite_bounded_utf8_commands(self):
        data = encode_command({"text": "原生编辑器\n"})
        self.assertEqual(data.count(b"\n"), 1)
        self.assertEqual(json.loads(data), {"text": "原生编辑器\n"})
        with self.assertRaises(ValueError):
            encode_command({"value": float("nan")})
        with self.assertRaises(ValueError):
            encode_command({"html": "a" * 1048576})


CHILD = r"""
import json,struct,sys,time
def send(message,payload=b''):
    header=json.dumps(message).encode()
    sys.stdout.buffer.write(struct.pack('<II',len(header),len(payload))+header+payload)
    sys.stdout.buffer.flush()
send({'type':'ready','protocol':1})
for line in sys.stdin.buffer:
    command=json.loads(line)
    if command['type']=='shutdown':break
    if command['type']=='create':
        base={'surface_id':command['surface_id'],'generation':command['generation']}
        send({'type':'call','id':'roundtrip','method':'test.echo','params':{'text':'hello'},**base})
        for sequence in (0,1):
            send({'type':'frame','seq':sequence,'width':2,'height':1,'stride':8,
                  'format':'rgba8','alpha':'straight','origin':'top-left','resize_revision':0,**base},b'12345678')
    elif command['type']=='call_result':
        send({'type':'event','surface_id':command['surface_id'],'generation':command['generation'],
              'event':'roundtrip','detail':command.get('result')})
"""


@unittest.skipIf(
    os.name == "nt" and sys.version_info < (3, 12), "Windows pipes require Python3.12+"
)
class ProcessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "main.cjs").write_text("test sentinel", encoding="utf-8")
        (root / "stdio.cjs").write_text(CHILD, encoding="utf-8")
        self.client = RendererProcess(sys.executable, root)

        def cleanup():
            self.client.terminate()
            self.client._process.wait(timeout=3)  # Test observes actual owned-process exit.

        self.addCleanup(cleanup)

    def until(self, predicate, timeout=5):
        messages = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            messages.extend(self.client.poll())
            if predicate(messages):
                return messages
            time.sleep(0.005)
        self.fail(f"Child condition timed out: {messages}, {self.client.last_error}")

    def test_nonblocking_roundtrip_frames_and_shutdown(self):
        self.client.create("one", 1, 2, 1, html="<p>live</p>")
        messages = self.until(
            lambda items: (
                any(item["type"] == "call" for item in items)
                and any(item["type"] == "frame" for item in items)
            )
        )
        self.assertTrue(self.client.ready)
        self.assertEqual([item["seq"] for item in messages if item["type"] == "frame"], [1])
        self.client.call_result("one", 1, "roundtrip", True, result={"hello": "world"})
        messages = self.until(lambda items: any(item["type"] == "event" for item in items))
        self.assertEqual(messages[-1]["detail"], {"hello": "world"})
        self.client.shutdown()
        self.until(lambda _: self.client.closed)
        self.assertFalse(self.client.alive)

    def test_expired_generation_and_bounded_queue(self):
        self.client.create("one", 1, 2, 1, html="test")
        self.client.close_surface("one", 1)
        with self.assertRaisesRegex(RuntimeError, "expired"):
            self.client.input("one", 1, {"type": "text", "text": "stale"})
        self.client.create("one", 2, 2, 1, html="new")
        for _ in range(252):
            self.client.input("one", 2, {"type": "text", "text": "x"})
        with self.assertRaisesRegex(RuntimeError, "queue is full"):
            self.client.input("one", 2, {"type": "text", "text": "overflow"})

    def test_crash_invalidates_surfaces_and_returns_typed_error(self):
        self.client._process.kill()
        messages = self.until(lambda items: any(item["type"] == "error" for item in items))
        self.assertEqual(messages[-1]["code"], "renderer_disconnected")
        with self.assertRaisesRegex(RuntimeError, "expired"):
            self.client.input("old", 1, {"type": "text", "text": "x"})


if __name__ == "__main__":
    unittest.main()
