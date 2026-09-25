"""Typed failures raised by SDK operations.

Every failure the platform reports maps to one class, so generated code can handle the cases
that matter (a stale revision, a missing record, a value the collection rejects) and let the
rest fail the run honestly.
"""

from __future__ import annotations

from typing import Any


class OperationError(Exception):
    """A platform operation failed. `code` is the platform's stable failure code."""

    code = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidValue(OperationError):
    code = "invalid_input"


class NotFound(OperationError):
    code = "not_found"


class Conflict(OperationError):
    """The record changed since it was read (stale revision), a unique value is taken, or an
    idempotency key was reused with different values."""

    code = "conflict"


class Forbidden(OperationError):
    code = "forbidden"


class LimitExceeded(OperationError):
    code = "limit_exceeded"


class Unavailable(OperationError):
    code = "unavailable"


_BY_CODE: dict[str, type[OperationError]] = {
    cls.code: cls
    for cls in (InvalidValue, NotFound, Conflict, Forbidden, LimitExceeded, Unavailable)
}


def from_reply(error: dict[str, Any] | None) -> OperationError:
    error = error or {}
    code = str(error.get("code", "internal_error"))
    message = str(error.get("message", "operation failed"))
    details = error.get("details") if isinstance(error.get("details"), dict) else None
    cls = _BY_CODE.get(code, OperationError)
    exc = cls(message, details)
    if cls is OperationError:
        exc.code = code
    return exc
