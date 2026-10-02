"""Provider API keys, kept in the macOS login Keychain — never in a plaintext file, localStorage
or a log. Each provider gets one generic-password item (`alpha.<provider>`, account `alpha`).

The value is never passed as a subprocess argv: `security -i` reads a single command line from
stdin, so the key never shows up in `ps` output the way `security ... -w <key>` would.
"""

from __future__ import annotations

import subprocess

_SERVICE_PREFIX = "alpha."
_ACCOUNT = "alpha"


class KeychainError(Exception):
    pass


def _service(provider: str) -> str:
    return f"{_SERVICE_PREFIX}{provider}"


def _quote(value: str) -> str:
    """Double-quote `value` for `security`'s command-line-style stdin parser."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_key(provider: str, key: str) -> None:
    """Save (or replace, `-U`) the key for `provider`."""
    key = key.strip()
    if not key:
        raise KeychainError("the key is empty")
    if "\n" in key or "\r" in key:
        raise KeychainError("the key cannot contain a newline")
    command = (
        f"add-generic-password -U -s {_quote(_service(provider))} "
        f"-a {_quote(_ACCOUNT)} -w {_quote(key)}\n"
    )
    try:
        proc = subprocess.run(
            ["security", "-i"], input=command, text=True, capture_output=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KeychainError(f"could not reach the Keychain: {exc}") from exc
    if proc.returncode != 0:
        raise KeychainError((proc.stderr or proc.stdout).strip() or "could not save the key")


def get_key(provider: str) -> str | None:
    """The saved key for `provider`, or None when nothing is saved."""
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", _service(provider), "-a", _ACCOUNT, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip("\n")
    return value or None


def has_key(provider: str) -> bool:
    return get_key(provider) is not None


def delete_key(provider: str) -> None:
    """Remove the saved key for `provider`. Never an error when there was none."""
    try:
        subprocess.run(
            ["security", "delete-generic-password", "-s", _service(provider), "-a", _ACCOUNT],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KeychainError(f"could not reach the Keychain: {exc}") from exc


def last4(provider: str) -> str | None:
    """The last 4 characters of the saved key, for display (`•••• ab12`) — the key itself is
    never returned to a caller outside this module's own get_key()."""
    key = get_key(provider)
    return key[-4:] if key else None


def demo() -> None:  # ponytail: smallest runnable self-check, exercised via a fake `security`
    import os
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "security")
        store = os.path.join(tmp, "store.txt")
        with open(fake, "w") as f:
            f.write(
                "#!/bin/sh\n"
                'if [ "$1" = "-i" ]; then\n'
                "  read -r line\n"
                "  case \"$line\" in\n"
                "    add-generic-password*)\n"
                "      echo \"$line\" | sed -n 's/.*-w \"\\(.*\\)\".*/\\1/p' > "
                f'"{store}" ;;\n'
                "  esac\n"
                'elif [ "$1" = "find-generic-password" ]; then\n'
                f'  [ -f "{store}" ] && cat "{store}" || exit 44\n'
                'elif [ "$1" = "delete-generic-password" ]; then\n'
                f'  rm -f "{store}"\n'
                "fi\n"
            )
        os.chmod(fake, 0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = tmp + os.pathsep + old_path
        try:
            assert get_key("demo") is None
            set_key("demo", "sk-abc123")
            assert get_key("demo") == "sk-abc123"
            assert has_key("demo")
            assert last4("demo") == "c123"
            delete_key("demo")
            assert get_key("demo") is None
        finally:
            os.environ["PATH"] = old_path
    print("keychain demo: ok", file=sys.stderr)


if __name__ == "__main__":
    demo()
