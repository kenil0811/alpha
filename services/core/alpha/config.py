"""Core settings supplied by the native host through an allowlisted environment.

Nothing here is read from the user's shell profile: the host passes exactly these variables.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class CoreSettings:
    data_dir: Path
    session_token: str
    allowed_origins: frozenset[str]
    host: str = "127.0.0.1"
    port: int = 0
    worker_python: Path = field(default_factory=lambda: Path(sys.executable))
    worker_grace_seconds: float = 2.0
    default_timeout_seconds: int = 60
    workspace_id: str = "ws_local"
    enabled_model_routes: frozenset[str] = frozenset({"fake"})
    builder_path: str = "/usr/bin:/bin"
    builder_home: str | None = None
    build_max_attempt_seconds: int | None = None
    assistant_route: str = "fake"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> CoreSettings:
        env = dict(os.environ if env is None else env)
        try:
            data_dir = Path(env["ALPHA_DATA_DIR"])
            token = env["ALPHA_SESSION_TOKEN"]
            origins = env["ALPHA_ALLOWED_ORIGINS"]
        except KeyError as exc:  # pragma: no cover - exercised by main() error path
            raise ConfigError(f"missing required environment variable {exc.args[0]}") from exc
        if len(token) < 32:
            raise ConfigError("ALPHA_SESSION_TOKEN must be at least 32 characters")
        allowed = frozenset(o.strip() for o in origins.split(",") if o.strip())
        if not allowed:
            raise ConfigError("ALPHA_ALLOWED_ORIGINS must list at least one origin")
        port = int(env.get("ALPHA_PORT", "0"))
        grace = float(env.get("ALPHA_WORKER_GRACE_SECONDS", "2.0"))
        routes = frozenset(
            r.strip() for r in env.get("ALPHA_ENABLED_MODEL_ROUTES", "fake").split(",") if r.strip()
        )
        assistant_route = env.get("ALPHA_ASSISTANT_ROUTE") or (
            "claude-code-cli" if "claude-code-cli" in routes else "fake"
        )
        return cls(
            data_dir=data_dir,
            session_token=token,
            allowed_origins=allowed,
            port=port,
            worker_grace_seconds=grace,
            enabled_model_routes=routes,
            builder_path=env.get("ALPHA_BUILDER_PATH", "/usr/bin:/bin"),
            builder_home=env.get("ALPHA_BUILDER_HOME") or None,
            assistant_route=assistant_route,
            build_max_attempt_seconds=(
                int(env["ALPHA_BUILD_MAX_ATTEMPT_SECONDS"])
                if env.get("ALPHA_BUILD_MAX_ATTEMPT_SECONDS")
                else None
            ),
        )

    @property
    def control_db_path(self) -> Path:
        return self.data_dir / "control.sqlite"

    @property
    def scratch_root(self) -> Path:
        return self.data_dir / "scratch"

    @property
    def builds_root(self) -> Path:
        return self.data_dir / "builds"
