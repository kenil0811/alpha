"""The one failure type trusted capability services raise.

Codes are the capability protocol's failure classes (Current Release Specification §7); the
broker turns an OperationFailed into a failed reply, the API into an HTTP status.
"""

from __future__ import annotations

from typing import Any, Literal

FailureCode = Literal[
    "invalid_input",
    "not_found",
    "conflict",
    "forbidden",
    "unauthenticated",
    "limit_exceeded",
    "unavailable",
    "timed_out",
    "internal_error",
]

HTTP_STATUS: dict[str, int] = {
    "invalid_input": 422,
    "not_found": 404,
    "conflict": 409,
    "forbidden": 403,
    "unauthenticated": 401,
    "limit_exceeded": 422,
    "unavailable": 503,
    "timed_out": 504,
    "internal_error": 500,
}


class OperationFailed(Exception):
    def __init__(
        self, code: FailureCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code: FailureCode = code
        self.message = message
        self.details = details or {}

    def as_error(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message[:2000], "details": self.details}


def invalid(message: str, **details: Any) -> OperationFailed:
    return OperationFailed("invalid_input", message, details)


def not_found(message: str, **details: Any) -> OperationFailed:
    return OperationFailed("not_found", message, details)


def conflict(message: str, **details: Any) -> OperationFailed:
    return OperationFailed("conflict", message, details)


def forbidden(message: str, **details: Any) -> OperationFailed:
    return OperationFailed("forbidden", message, details)


def limit(message: str, **details: Any) -> OperationFailed:
    return OperationFailed("limit_exceeded", message, details)


def unavailable(message: str, **details: Any) -> OperationFailed:
    return OperationFailed("unavailable", message, details)
