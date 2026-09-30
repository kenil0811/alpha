"""ModelGateway: route registry, budget policy and usage accounting.

Routes are configuration, not code paths generated per App. A route is enabled only when the
host lists it in ALPHA_ENABLED_MODEL_ROUTES; live routes never turn on implicitly. Cost is
recorded with its basis: provider-reported, subscription-unmetered (the CLI route: the number
the CLI reports is a provider-equivalent estimate, not a charge) or unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from alpha_contracts.builds import BuildBudget, BuildUsage, CostBasis

from alpha.models.preferences import Preferences
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
# attempt, 30 minutes total including repair, at most two automatic repair attempts.
DEFAULT_BUDGET = {
    # A complete first version (detail pages, freshness, filters, a resolved source) needs
    # more turns than a minimal one; the time caps move a little with it.
    "max_turns": 90,
    "max_attempt_seconds": 900,
    "max_total_seconds": 2400,
    "max_repair_attempts": 2,
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
            "default auth is a Console account sign-in (`claude` -> /login); an Anthropic API "
            "key saved in Settings -> Models is used instead only when chosen there",
        ),
    ),
    "chatgpt-codex-cli": ModelRoute(
        route_id="chatgpt-codex-cli",
        provider="openai-codex-cli",
        model="default",
        cost_basis=CostBasis.SUBSCRIPTION_UNMETERED,
        harness="codex-cli",
        live=True,
        notes=("ChatGPT sign-in owned by the Codex CLI (`codex login`); the person's choice",),
    ),
    "chatgpt-api": ModelRoute(
        route_id="chatgpt-api",
        provider="openai-api",
        model="gpt-4o-mini",
        cost_basis=CostBasis.PROVIDER_REPORTED,
        harness="openai-http",
        live=True,
        notes=("uses the OpenAI API key saved in Settings -> Models",),
    ),
    "openrouter": ModelRoute(
        route_id="openrouter",
        provider="openrouter",
        model="openai/gpt-4o-mini",
        cost_basis=CostBasis.PROVIDER_REPORTED,
        harness="openai-http",
        live=True,
        notes=("uses the OpenRouter key and model id saved in Settings -> Models",),
    ),
    "grok": ModelRoute(
        route_id="grok",
        provider="xai-grok",
        model="grok-4",
        cost_basis=CostBasis.PROVIDER_REPORTED,
        harness="openai-http",
        live=True,
        notes=("uses the xAI key saved in Settings -> Models",),
    ),
}

# The provider the person chose in Settings -> Models (`models.provider`) maps onto one of the
# routes above; when set to a non-Claude choice, it overrides the route_id a stage would
# otherwise use (the desktop host's static ALPHA_ASSISTANT_ROUTE / ALPHA_BUILDER_ROUTE / etc).
PROVIDER_ROUTE_ID: dict[str, str] = {
    "claude": "claude-code-cli",
    "chatgpt_codex": "chatgpt-codex-cli",
    "chatgpt_api": "chatgpt-api",
    "openrouter": "openrouter",
    "grok": "grok",
}

# For every non-Claude live route, the one preference holding the model id to use — there is no
# per-stage choice for these the way Claude has opus/sonnet/haiku.
MODEL_PREFERENCE_BY_ROUTE: dict[str, str] = {
    "chatgpt-api": "models.chatgpt_model",
    "openrouter": "models.openrouter_model",
    "grok": "models.grok_model",
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
        max_total_seconds: int | None = None,
        preferences: Preferences | None = None,
    ) -> None:
        self._store = store
        self._enabled = enabled_routes
        # What the person chose in Settings (model per stage, build limits); None in tests.
        self.preferences = preferences
        self._max_attempt_seconds = max_attempt_seconds or int(
            DEFAULT_BUDGET["max_attempt_seconds"]
        )
        self._max_total_seconds = max_total_seconds or int(DEFAULT_BUDGET["max_total_seconds"])
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

    def route(self, route_id: str, stage: str | None = None) -> ModelRoute:
        """The route, with the model the person chose in Settings when the route can take one.
        For a `stage` (assistant, planner, builder_new, builder_change or app), `models.provider`
        first picks which route actually runs; on Claude, `models.{stage}` then picks
        opus/sonnet/haiku, otherwise the route's own single model preference applies."""
        route = ROUTES.get(route_id)
        if route is None:
            raise RouteUnavailable(f"unknown model route {route_id!r}")
        # Only a *live* default route (what the host configured for this stage) is subject to the
        # person's provider choice; a caller asking for "fake" (control fixture, tests) always
        # gets exactly that, never silently swapped for a real provider.
        if stage and self.preferences is not None and route.live:
            chosen_provider = self.preferences.get("models.provider")
            override_id = PROVIDER_ROUTE_ID.get(str(chosen_provider))
            if override_id and override_id != route_id and override_id in ROUTES:
                route_id, route = override_id, ROUTES[override_id]
        if route_id not in self._enabled:
            raise RouteUnavailable(
                f"model route {route_id!r} is not enabled on this host (ALPHA_ENABLED_MODEL_ROUTES)"
            )
        if not (stage and self.preferences is not None and route.live):
            return route
        if route.route_id == "claude-code-cli":
            chosen = self.preferences.get(f"models.{stage}")
            if chosen and chosen != "default":
                return replace(route, model=str(chosen))
            return route
        model_pref = MODEL_PREFERENCE_BY_ROUTE.get(route.route_id)
        if model_pref:
            chosen = self.preferences.get(model_pref)
            if chosen:
                return replace(route, model=str(chosen))
        return route

    def budget(self, route: ModelRoute, max_cost_usd: float | None = None) -> BuildBudget:
        if route.cost_basis is CostBasis.PROVIDER_REPORTED and max_cost_usd is None:
            raise RouteUnavailable(
                f"route {route.route_id!r} is metered; an explicit max_cost_usd is required"
            )
        prefs = self.preferences
        if prefs is not None:
            # The person's limits, never above the host's caps (tests and operators set those).
            return BuildBudget(
                max_turns=int(prefs.get("build.max_turns")),
                max_attempt_seconds=min(
                    int(prefs.get("build.max_attempt_minutes")) * 60, self._max_attempt_seconds
                ),
                max_total_seconds=max(
                    1, min(int(prefs.get("build.max_total_minutes")) * 60, self._max_total_seconds)
                ),
                max_repair_attempts=int(prefs.get("build.max_repair_attempts")),
                max_cost_usd=max_cost_usd,
                cost_basis=route.cost_basis,
            )
        return BuildBudget(
            max_turns=int(DEFAULT_BUDGET["max_turns"]),
            max_attempt_seconds=self._max_attempt_seconds,
            max_total_seconds=max(self._max_total_seconds, 1),
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
