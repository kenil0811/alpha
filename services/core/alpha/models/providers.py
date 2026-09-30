"""Stdlib HTTP calls to OpenAI-compatible providers (OpenAI, OpenRouter, xAI Grok). Core has no
HTTP client dependency, so this uses `urllib.request` rather than adding one."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from alpha_contracts.builds import BuildUsage, CostBasis


class ProviderHTTPError(Exception):
    """A provider call failed: bad key, network error, or a malformed/non-conforming answer.
    The message is plain language, safe to show as-is."""


def _request(
    url: str, api_key: str, body: dict[str, Any] | None, timeout: int
) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if body is not None else "GET",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code in (401, 403):
            raise ProviderHTTPError("The key was rejected. Check it and try again.") from exc
        raise ProviderHTTPError(f"The provider returned an error ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderHTTPError(f"Could not reach the provider: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderHTTPError("The provider took too long to answer.") from exc


def probe(base_url: str, api_key: str, timeout: int = 10) -> None:
    """A cheap authenticated call (list models) used only to prove a key works. Raises
    ProviderHTTPError on failure; returns nothing on success."""
    _request(f"{base_url}/models", api_key, None, timeout)


def chat_structured(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    schema: dict[str, Any],
    timeout: int = 120,
) -> tuple[dict[str, Any], BuildUsage, int]:
    """One structured chat completion against an OpenAI-compatible /chat/completions endpoint.
    Returns (parsed JSON output, usage, elapsed_ms). Raises ProviderHTTPError on any failure:
    network, auth, a non-2xx response, or an answer that isn't the requested JSON object."""
    started = time.monotonic()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "result", "strict": True, "schema": schema},
        },
    }
    result = _request(f"{base_url}/chat/completions", api_key, body, timeout)
    elapsed = int((time.monotonic() - started) * 1000)
    choices = result.get("choices") or []
    if not choices:
        raise ProviderHTTPError("The provider returned no answer.")
    content = choices[0].get("message", {}).get("content", "")
    try:
        output = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderHTTPError("The provider's answer was not valid JSON.") from exc
    if not isinstance(output, dict):
        raise ProviderHTTPError("The provider's answer was not a JSON object.")
    usage_raw = result.get("usage") or {}
    usage = BuildUsage(
        input_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
        turns=1,
        duration_ms=elapsed,
        cost_basis=CostBasis.PROVIDER_REPORTED,
        models={
            model: {
                "inputTokens": usage_raw.get("prompt_tokens"),
                "outputTokens": usage_raw.get("completion_tokens"),
            }
        },
    )
    return output, usage, elapsed
