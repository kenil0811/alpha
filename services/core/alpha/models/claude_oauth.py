"""Claude sign-in without a terminal, the way Bridge does it: the same public OAuth PKCE flow
`claude login` uses. Core opens the authorize page in the browser; the page shows a code the
person pastes back; Core exchanges it and keeps the tokens in the macOS Keychain (never a file,
never returned to the UI). Model calls hand the access token to the `claude` CLI as
CLAUDE_CODE_OAUTH_TOKEN (structured.py), refreshing it here when it is about to expire.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from alpha.models import keychain

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code's public OAuth client
AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
REDIRECT = "https://console.anthropic.com/oauth/code/callback"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
SCOPE = "org:create_api_key user:profile user:inference"
KEYCHAIN_ID = "claude_oauth"

# ponytail: one sign-in in flight per Core; a second Sign in replaces the first.
_verifier: str | None = None


class OAuthError(Exception):
    """Plain language, safe to show as-is; never carries a token."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def authorize_url() -> str:
    """Start a sign-in: a fresh PKCE verifier, and the page to open."""
    global _verifier
    _verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(_verifier.encode()).digest())
    query = urllib.parse.urlencode(
        {
            "code": "true",
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT,
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": _verifier,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def open_in_browser(url: str) -> None:
    subprocess.run(["/usr/bin/open", url], check=False, timeout=10)  # noqa: S603 - fixed binary


def finish(pasted: str) -> None:
    """Exchange the "code#state" the callback page shows for tokens, kept in the Keychain."""
    global _verifier
    if not _verifier:
        raise OAuthError("Press Sign in first, then paste the code it shows.")
    code, _, state = pasted.strip().partition("#")
    if not code:
        raise OAuthError("Paste the code the sign-in page shows.")
    _save(
        _token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "state": state or _verifier,
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT,
                "code_verifier": _verifier,
            }
        )
    )
    _verifier = None


def signed_in() -> bool:
    return keychain.get_key(KEYCHAIN_ID) is not None


def sign_out() -> None:
    keychain.delete_key(KEYCHAIN_ID)


def access_token() -> str | None:
    """A valid access token, refreshed through the token endpoint when stale; None if signed out
    or the refresh was refused (the person signs in again)."""
    raw = keychain.get_key(KEYCHAIN_ID)
    if not raw:
        return None
    tokens = json.loads(raw)
    if time.time() > tokens["expires"] - 60:
        try:
            tokens = _save(
                _token_request(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": tokens["refresh"],
                        "client_id": CLIENT_ID,
                    }
                )
            )
        except OAuthError:
            return None
    return str(tokens["access"])


def _token_request(body: dict[str, str]) -> dict[str, object]:
    req = urllib.request.Request(
        TOKEN_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed https host
            return dict(json.loads(resp.read().decode()))
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401):
            raise OAuthError("That code didn't work. Press Sign in and try a fresh one.") from exc
        raise OAuthError(f"Claude's sign-in answered with an error ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OAuthError("Couldn't reach Claude's sign-in. Check the connection.") from exc


def _save(tok: dict[str, object]) -> dict[str, object]:
    tokens = {
        "access": tok["access_token"],
        "refresh": tok["refresh_token"],
        "expires": time.time() + float(str(tok["expires_in"])),
    }
    keychain.set_key(KEYCHAIN_ID, json.dumps(tokens, separators=(",", ":")))
    return tokens


def demo() -> None:  # ponytail: smallest runnable self-check (no network, no Keychain)
    url = authorize_url()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["code_challenge_method"] == ["S256"]
    assert _verifier and query["state"] == [_verifier]
    challenge = _b64(hashlib.sha256(_verifier.encode()).digest())
    assert query["code_challenge"] == [challenge]
    print("claude_oauth demo: ok")


if __name__ == "__main__":
    demo()
