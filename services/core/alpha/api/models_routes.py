"""Settings -> Models: provider accounts (sign-in state, keys in the Keychain, a live test)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from alpha.models.accounts import ModelAccounts, UnknownProvider
from alpha.models.keychain import KeychainError


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=400)


def register(app: FastAPI, accounts: ModelAccounts) -> None:
    @app.get("/api/model-accounts")
    def list_accounts() -> dict[str, Any]:
        return {"providers": accounts.list_providers()}

    @app.put("/api/model-accounts/{provider}/key")
    def save_key(provider: str, body: KeyRequest) -> dict[str, Any]:
        try:
            return {"provider": accounts.save_key(provider, body.key)}
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except KeychainError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.delete("/api/model-accounts/{provider}/key")
    def remove_key(provider: str) -> dict[str, Any]:
        try:
            return {"provider": accounts.remove_key(provider)}
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except KeychainError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/model-accounts/{provider}/test")
    def test_connection(provider: str) -> dict[str, Any]:
        try:
            return accounts.test_connection(provider)
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
