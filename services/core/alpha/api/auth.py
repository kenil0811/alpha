"""Trusted-shell request authentication for the loopback transport.

Loopback location is not authentication. Every /api request must carry the host-issued session
token as a bearer credential, its Host header must be a loopback authority, and a browser-supplied
Origin must be one the host approved for this session.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        return None
    return credential.strip()


def make_auth_middleware(
    session_token: str, allowed_origins: frozenset[str]
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    expected = session_token.encode("utf-8")

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        host = request.headers.get("host", "").rsplit(":", 1)[0]
        if host not in _LOOPBACK_HOSTS:
            return JSONResponse({"error": "forbidden_host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            return JSONResponse({"error": "forbidden_origin"}, status_code=403)
        presented = _bearer(request)
        if presented is None or not hmac.compare_digest(presented.encode("utf-8"), expected):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    return middleware
