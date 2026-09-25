"""ModelGateway: route registry, budget policy and usage accounting.

Routes are configuration, not code paths generated per App. A route is enabled only when the
host lists it in ALPHA_ENABLED_MODEL_ROUTES; live routes never turn on implicitly. Cost is
recorded with its basis: provider-reported, subscription-unmetered (the CLI route: the number
the CLI reports is a provider-equivalent estimate, not a charge) or unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from alpha_contracts.builds import BuildBudget, BuildUsage, CostBasis

from alpha.storage.control_store import ControlStore, new_id, utc_now


@dataclass(frozen=True)
class ModelRoute:
    route_id: str
    provider: str
    model: str
    cost_basis: CostBasis
    harness: str
    live: bool
    notes: tuple[str, ...] = ()


# Initial qualification defaults from Prototype_Scope_and_Acceptance section 7: 12 minutes per
# attempt, 30 minutes total; automatic repair arrives with F07 (0 here).
DEFAULT_BUDGET = {
    "max_turns": 40,
    "max_attempt_seconds": 720,
    "max_total_seconds": 1800,
    "max_repair_attempts": 0,
}

ROUTES: dict[str, ModelRoute] = {
    "fake": ModelRoute(
        route_id="fake",
        provider="fake",
        model="none",
        cost_basis=CostBasis.UNAVAILABLE,
        harness="fake",
        live=False,
        notes=("deterministic control fixture; proves lifecycle only",),
    ),
    "claude-code-cli": ModelRoute(
        route_id="claude-code-cli",
        provider="anthropic-claude-code-cli",
        model="default",
        cost_basis=CostBasis.SUBSCRIPTION_UNMETERED,
        harness="claude-code-cli",
        live=True,
        notes=(
            "founder decision 2026-09-25: subscription login owned by the CLI; internal use only",
            "reported cost is a provider-equivalent estimate, not a charge",
        ),
    ),
}


class RouteUnavailable(Exception):
    pass


class ModelGateway:
    def __init__(
        self,
        store: ControlStore,
        enabled_routes: frozenset[str],
        *,
        max_attempt_seconds: int | None = None,
    ) -> None:
        self._store = store
        self._enabled = enabled_routes
        self._max_attempt_seconds = max_attempt_seconds or int(
            DEFAULT_BUDGET["max_attempt_seconds"]
        )
        store.execute_script(
            """
                CREATE TABLE IF NOT EXISTS model_usage (
                    usage_id TEXT PRIMARY KEY,
                    route_id TEXT NOT NULL,
                    scope_kind TEXT NOT NULL,
                    scope_ref TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cache_read_input_tokens INTEGER NOT NULL,
                    cache_creation_input_tokens INTEGER NOT NULL,
                    turns INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    cost_usd REAL,
                    cost_basis TEXT NOT NULL,
                    models_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS model_usage_scope_idx
                    ON model_usage(scope_kind, scope_ref);
                """
        )

    def routes(self) -> list[dict[str, Any]]:
        return [
            {
                "route_id": r.route_id,
                "provider": r.provider,
                "model": r.model,
                "cost_basis": r.cost_basis.value,
                "harness": r.harness,
                "live": r.live,
                "enabled": r.route_id in self._enabled,
                "notes": list(r.notes),
            }
            for r in ROUTES.values()
        ]

    def route(self, route_id: str) -> ModelRoute:
        route = ROUTES.get(route_id)
        if route is None:
            raise RouteUnavailable(f"unknown model route {route_id!r}")
        if route_id not in self._enabled:
            raise RouteUnavailable(
                f"model route {route_id!r} is not enabled on this host (ALPHA_ENABLED_MODEL_ROUTES)"
            )
        return route

    def budget(self, route: ModelRoute, max_cost_usd: float | None = None) -> BuildBudget:
        if route.cost_basis is CostBasis.PROVIDER_REPORTED and max_cost_usd is None:
            raise RouteUnavailable(
                f"route {route.route_id!r} is metered; an explicit max_cost_usd is required"
            )
        return BuildBudget(
            max_turns=int(DEFAULT_BUDGET["max_turns"]),
            max_attempt_seconds=self._max_attempt_seconds,
            max_total_seconds=int(DEFAULT_BUDGET["max_total_seconds"]),
            max_repair_attempts=int(DEFAULT_BUDGET["max_repair_attempts"]),
            max_cost_usd=max_cost_usd,
            cost_basis=route.cost_basis,
        )

    def record_usage(
        self, route_id: str, scope_kind: str, scope_ref: str, usage: BuildUsage
    ) -> str:
        usage_id = new_id("usage")
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO model_usage(usage_id, route_id, scope_kind, scope_ref, input_tokens,
                   output_tokens, cache_read_input_tokens, cache_creation_input_tokens, turns,
                   duration_ms, cost_usd, cost_basis, models_json, recorded_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    usage_id,
                    route_id,
                    scope_kind,
                    scope_ref,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.cache_read_input_tokens,
                    usage.cache_creation_input_tokens,
                    usage.turns,
                    usage.duration_ms,
                    usage.cost_usd,
                    usage.cost_basis.value,
                    json.dumps(usage.models, sort_keys=True),
                    utc_now().isoformat().replace("+00:00", "Z"),
                ),
            )
        return usage_id

    def usage_for(self, scope_kind: str, scope_ref: str) -> list[dict[str, Any]]:
        rows = self._store.query(
            "SELECT * FROM model_usage WHERE scope_kind = ? AND scope_ref = ? ORDER BY recorded_at",
            (scope_kind, scope_ref),
        )
        return [dict(r) for r in rows]
