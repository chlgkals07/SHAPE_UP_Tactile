"""Custom exception hierarchy for the Paxini SDK."""


class PaxiniError(Exception):
    """Base class for all SDK errors."""


class FrameError(PaxiniError):
    """Raised when a received frame is malformed (wrong header, truncated, etc.)."""


class LRCError(FrameError):
    """Raised when LRC checksum verification fails."""


class DeviceError(PaxiniError):
    """Raised when the device returns a non-zero error code in a response frame."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class TimeoutError(PaxiniError):  # noqa: A001 — intentionally shadows builtin within package scope
    """Raised when no response is received within the configured timeout."""
