"""Nonblocking child-process transport. The host owns when poll() runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

from ._job import ProcessTree
from ._pipes import OutputPipe
from .protocol import MAX_SURFACES, FrameDecoder, ProtocolError, encode_command


def resolve_bundle(path: str | Path) -> tuple[Path, Path]:
    """Validate a maintainer-built bundle's launch paths and critical files.

    Full publisher/archive integrity is verified by the acquisition/build tool.
    This startup check verifies launch files against the bundled inventory.
    """
    root = Path(path).expanduser().resolve(strict=True)
    manifest = json.loads((root / "bundle-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported AuroraView renderer bundle")
    launch = manifest["launch"]

    def member(relative: str) -> Path:
        candidate = (root / relative).resolve(strict=True)
        if not candidate.is_relative_to(root):
            raise ValueError("Renderer bundle path escapes its directory")
        return candidate

    executable, helper = member(launch["executable"]), member(launch["helper"])
    if not executable.is_file() or not helper.is_dir():
        raise ValueError("Renderer bundle requires an executable and helper directory")
    for relative in (
        launch["executable"],
        f"{launch['helper']}/main.cjs",
        f"{launch['helper']}/preload.cjs",
        f"{launch['helper']}/event_bridge.js",
        f"{launch['helper']}/stdio.cjs",
        f"{launch['helper']}/protocol.cjs",
        f"{launch['helper']}/protocol.json",
        f"{launch['helper']}/pixels.cjs",
        f"{launch['helper']}/input.cjs",
        f"{launch['helper']}/package.json",
    ):
        source = member(relative)
        expected = manifest["files"][relative]
        if (
            source.stat().st_size != expected["size"]
            or hashlib.sha256(source.read_bytes()).hexdigest() != expected["sha256"]
        ):
            raise ValueError(f"Renderer bundle integrity check failed: {relative}")
    return executable, helper


class RendererProcess:
    """One private renderer, with bounded messages and generation-scoped surfaces.

    No background Python thread, host API call, listener, nested event loop or
    blocking wait is introduced. Call poll() from the host's existing timer.
    """

    def __init__(
        self,
        executable: str | Path,
        helper_dir: str | Path,
        *,
        log_path: str | Path | None = None,
        startup_timeout: float = 15.0,
    ):
        if os.name == "nt" and sys.version_info < (3, 12):
            raise RuntimeError("Windows offscreen transport requires Python 3.12 or newer")
        if not 0 < startup_timeout <= 60:
            raise ValueError("startup_timeout must be within (0, 60] seconds")
        executable, helper_dir = Path(executable).resolve(), Path(helper_dir).resolve()
        if not executable.is_file() or not all(
            (helper_dir / name).is_file() for name in ("main.cjs", "stdio.cjs")
        ):
            raise ValueError("Select a complete AuroraView renderer bundle")
        self._log = open(log_path, "ab", buffering=0) if log_path else None
        env = dict(os.environ)
        env["ELECTRON_RUN_AS_NODE"] = "1"
        env["ELECTRON_NO_ATTACH_CONSOLE"] = "1"
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        output_pipe = None
        try:
            # Popen's default Windows anonymous pipe is about 4 KiB. A larger
            # burst buffer lets the existing timer drain frames without waiting
            # hundreds of ticks for a blocked writer to refill that small pipe.
            output_pipe = OutputPipe() if os.name == "nt" else None
            self._process = subprocess.Popen(
                [str(executable), str(helper_dir / "stdio.cjs")],
                stdin=subprocess.PIPE,
                stdout=output_pipe.writer if output_pipe else subprocess.PIPE,
                stderr=self._log or subprocess.DEVNULL,
                bufsize=0,
                env=env,
                creationflags=flags,
                start_new_session=os.name != "nt",
            )
            if output_pipe:
                self._process.stdout = output_pipe.take_reader()
            self._tree = ProcessTree(self._process)
            os.set_blocking(self._process.stdin.fileno(), False)
            os.set_blocking(self._process.stdout.fileno(), False)
        except BaseException:
            try:
                if hasattr(self, "_tree"):
                    self._tree.close(force=True)
                elif hasattr(self, "_process"):
                    self._process.kill()
                    self._process.wait(timeout=0.25)
            finally:
                if hasattr(self, "_process"):
                    self._process.stdin.close()
                    self._process.stdout.close()
                if self._log:
                    self._log.close()
            raise
        finally:
            if output_pipe:
                output_pipe.close()
        self._decoder = FrameDecoder()
        self._outgoing: deque[bytes] = deque()
        self._queued_bytes = 0
        self._surfaces: dict[str, int] = {}
        self._sequences: dict[str, int] = {}
        self._started = time.monotonic()
        self._startup_timeout = startup_timeout
        self._shutdown_at: float | None = None
        self.ready = False
        self.closed = False
        self._cleanup_pending = False
        self.last_error: str | None = None
        # The broker cannot create Chromium descendants until the owner has
        # assigned its process tree and established the nonblocking transport.
        self._send({"type": "start"})

    @property
    def pid(self) -> int:
        return self._process.pid

    @property
    def alive(self) -> bool:
        return not self.closed and self._process.poll() is None

    @property
    def pending_bytes(self) -> int:
        return self._queued_bytes

    def _send(self, command: dict[str, Any]) -> None:
        if self.closed or self._cleanup_pending or self._shutdown_at is not None:
            raise RuntimeError("Renderer connection is closed")
        data = encode_command(command)
        if len(self._outgoing) >= 256 or self._queued_bytes + len(data) > 4 * 1024 * 1024:
            raise RuntimeError("Renderer command queue is full")
        self._outgoing.append(data)
        self._queued_bytes += len(data)

    def _surface_command(self, kind: str, surface_id: str, generation: int, **fields) -> None:
        if self._surfaces.get(surface_id) != generation:
            raise RuntimeError("Renderer surface belongs to an expired generation")
        self._send({"type": kind, "surface_id": surface_id, "generation": generation, **fields})

    def create(
        self,
        surface_id: str,
        generation: int,
        width: int,
        height: int,
        *,
        html: str | None = None,
        url: str | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", surface_id):
            raise ValueError("Invalid renderer surface identity")
        if type(generation) is not int or generation < 1:
            raise ValueError("Surface generation must be a positive integer")
        if surface_id in self._surfaces or len(self._surfaces) >= MAX_SURFACES:
            raise RuntimeError("Surface already exists or renderer surface limit reached")
        if (html is None) == (url is None):
            raise ValueError("Specify exactly one of html or url")
        self._surfaces[surface_id] = generation
        try:
            self._surface_command(
                "create",
                surface_id,
                generation,
                width=width,
                height=height,
                **({"html": html} if html is not None else {"url": url}),
            )
        except BaseException:
            self._surfaces.pop(surface_id, None)
            raise

    def resize(self, surface_id: str, generation: int, width: int, height: int) -> None:
        self._surface_command("resize", surface_id, generation, width=width, height=height)

    def input(self, surface_id: str, generation: int, event: dict[str, Any]) -> None:
        self._surface_command("input", surface_id, generation, event=event)

    def emit(self, surface_id: str, generation: int, event: str, detail: Any = None) -> None:
        self._surface_command("emit", surface_id, generation, event=event, detail=detail)

    def call_result(
        self,
        surface_id: str,
        generation: int,
        id: str,
        ok: bool,
        *,
        result: Any = None,
        error: dict | None = None,
    ) -> None:
        self._surface_command(
            "call_result",
            surface_id,
            generation,
            id=id,
            ok=ok,
            **({"result": result} if ok else {"error": error}),
        )

    def close_surface(self, surface_id: str, generation: int) -> None:
        self._surface_command("close", surface_id, generation)
        self._surfaces.pop(surface_id, None)
        self._sequences.pop(surface_id, None)

    def poll(self) -> list[dict[str, Any]]:
        """Pump at most 256 KiB outbound / 8 MiB inbound per host timer tick."""
        if self.closed:
            return []
        if self._cleanup_pending:
            return self._poll_cleanup()
        try:
            messages = self._pump()
            if self._shutdown_at is not None:
                if self._process.poll() is not None or time.monotonic() >= self._shutdown_at:
                    messages.extend(self._poll_cleanup())
            elif self._process.poll() is not None:
                raise RuntimeError(f"Renderer exited with code {self._process.returncode}")
            elif not self.ready and time.monotonic() - self._started > self._startup_timeout:
                raise RuntimeError("Renderer startup handshake timed out")
            return messages
        except (OSError, ProtocolError, RuntimeError) as exc:
            self.last_error = str(exc)
            return [
                {"type": "error", "code": "renderer_disconnected", "message": str(exc)}
            ] + self._poll_cleanup()

    def _poll_cleanup(self) -> list[dict[str, Any]]:
        """Attempt teardown once per tick, preserving ownership while the OS exits."""
        try:
            self.terminate()
        except TimeoutError as exc:
            return [{"type": "error", "code": "cleanup_pending", "message": str(exc)}]
        return []

    def _pump(self) -> list[dict[str, Any]]:
        budget = 256 * 1024
        while self._outgoing and budget:
            chunk = self._outgoing[0]
            try:
                written = os.write(self._process.stdin.fileno(), chunk[:budget])
            except BlockingIOError:
                break
            if not written:
                break
            budget -= written
            self._queued_bytes -= written
            if written == len(chunk):
                self._outgoing.popleft()
            else:
                self._outgoing[0] = chunk[written:]
        result = []
        frames = {}
        budget = 8 * 1024 * 1024
        while budget:
            try:
                data = os.read(self._process.stdout.fileno(), min(budget, 64 * 1024))
            except BlockingIOError:
                break
            if not data:
                break
            budget -= len(data)
            for message in self._decoder.feed(data):
                kind = message["type"]
                if kind == "ready":
                    if message.get("protocol") != 1:
                        raise ProtocolError("Renderer protocol version mismatch")
                    self.ready = True
                surface_id = message.get("surface_id")
                if surface_id is not None and self._surfaces.get(surface_id) != message.get(
                    "generation"
                ):
                    continue
                if kind == "frame":
                    if message["seq"] <= self._sequences.get(surface_id, -1):
                        continue
                    self._sequences[surface_id] = message["seq"]
                    frames[surface_id] = message
                else:
                    if len(result) >= 256:
                        raise ProtocolError("Renderer control message budget exceeded")
                    result.append(message)
        return result + list(frames.values())

    def shutdown(self) -> None:
        """Request graceful shutdown; subsequent poll() reaps within two seconds."""
        if self.closed or self._shutdown_at is not None:
            return
        self._send({"type": "shutdown"})
        self._shutdown_at = time.monotonic() + 2
        self._surfaces.clear()

    def terminate(self) -> None:
        """Close only our process tree, with a 250ms maximum OS reap budget."""
        if self.closed:
            return
        try:
            self._tree.close(force=True)
        except TimeoutError:
            self._cleanup_pending = True
            raise
        self._cleanup_pending = False
        self.closed = True
        self._process.stdin.close()
        self._process.stdout.close()
        if self._log:
            self._log.close()
        self._outgoing.clear()
        self._queued_bytes = 0
        self._surfaces.clear()

    def __del__(self):
        if hasattr(self, "closed"):
            self.terminate()
