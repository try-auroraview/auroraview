"""Optional AuroraView renderer transport; importing never starts a process."""

from .process import RendererCleanupError, RendererProcess, resolve_bundle
from .protocol import FrameDecoder, ProtocolError

__all__ = [
    "FrameDecoder",
    "ProtocolError",
    "RendererCleanupError",
    "RendererProcess",
    "resolve_bundle",
]
