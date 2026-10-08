"""Version-one bounded stdio envelope, independent of any DCC or renderer."""

from __future__ import annotations

import json
import struct
from typing import Any

MAX_HEADER = 64 * 1024
MAX_PAYLOAD = 64 * 1024 * 1024
MAX_COMMAND = 1024 * 1024
MAX_SURFACES = 8


class ProtocolError(RuntimeError):
    """The private renderer connection violated its framing contract."""


class FrameDecoder:
    """Incrementally decode complete envelopes without trusting peer lengths."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        if len(self._buffer) + len(data) > MAX_PAYLOAD + MAX_HEADER + 8:
            raise ProtocolError("Renderer receive buffer exceeded its budget")
        self._buffer.extend(data)
        messages = []
        offset = 0
        while len(self._buffer) - offset >= 8:
            header_size, payload_size = struct.unpack_from("<II", self._buffer, offset)
            if not 1 <= header_size <= MAX_HEADER or payload_size > MAX_PAYLOAD:
                raise ProtocolError("Invalid renderer envelope length")
            size = 8 + header_size + payload_size
            if len(self._buffer) - offset < size:
                break
            start = offset + 8
            try:
                header = json.loads(self._buffer[start : start + header_size])
            except (ValueError, UnicodeError) as exc:
                raise ProtocolError("Invalid renderer header JSON") from exc
            if not isinstance(header, dict) or not isinstance(header.get("type"), str):
                raise ProtocolError("Renderer message requires an object and type")
            payload = bytes(self._buffer[start + header_size : offset + size])
            if header["type"] == "frame":
                self._validate_frame(header, payload_size)
                header["payload"] = payload
            elif payload_size:
                raise ProtocolError("Only frame messages may carry binary data")
            messages.append(header)
            offset += size
        if offset:
            del self._buffer[:offset]
        return messages

    @staticmethod
    def _validate_frame(header: dict[str, Any], size: int) -> None:
        width, height = header.get("width"), header.get("height")
        if any(type(value) is not int or not 1 <= value <= 4096 for value in (width, height)):
            raise ProtocolError("Invalid frame dimensions")
        if header.get("stride") != width * 4 or size != width * height * 4:
            raise ProtocolError("Frame byte count does not match its dimensions")
        if (header.get("format"), header.get("alpha"), header.get("origin")) != (
            "rgba8",
            "straight",
            "top-left",
        ):
            raise ProtocolError("Unsupported renderer pixel format")
        for field in ("generation", "seq", "resize_revision"):
            if type(header.get(field)) is not int or header[field] < 0:
                raise ProtocolError(f"Invalid frame {field}")
        if not isinstance(header.get("surface_id"), str):
            raise ProtocolError("Frame requires a surface identity")


def encode_command(command: dict[str, Any]) -> bytes:
    try:
        data = (
            json.dumps(command, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("Renderer command must contain finite JSON values") from exc
    if len(data) > MAX_COMMAND:
        raise ValueError("Renderer command exceeds 1 MiB")
    return data
