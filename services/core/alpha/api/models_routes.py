"""Settings -> Models: provider accounts (sign-in state, keys in the Keychain, a live test)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from alpha.models.accounts import ModelAccounts, SignInUnavailable, UnknownProvider
from alpha.models.keychain import KeychainError
from alpha.models.preferences import InvalidSetting


class CodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=2000)


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=400)


class ModelPick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=100)


def register(app: FastAPI, accounts: ModelAccounts) -> None:
    @app.get("/api/model-accounts")
    def list_accounts() -> dict[str, Any]:
        return {"providers": accounts.list_providers()}

    @app.get("/api/model-accounts/{provider}/models")
    def list_models(provider: str) -> dict[str, Any]:
        """{"models": [{"id", "label"}], "selected": id | null}; an empty list when the
        provider can't be reached (no key, offline)."""
        try:
            return accounts.models(provider)
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/model-accounts/{provider}/model")
    def select_model(provider: str, body: ModelPick) -> dict[str, Any]:
        """Save the provider's selected model; returns the same shape as GET .../models."""
        try:
            return accounts.select_model(provider, body.model)
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidSetting as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SignInUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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

    @app.post("/api/model-accounts/{provider}/reconnect")
    def reconnect(provider: str) -> dict[str, Any]:
        """Disconnect (clear the key, or sign out) so the person can connect again at once."""
        try:
            return {"provider": accounts.reconnect(provider)}
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except KeychainError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/model-accounts/{provider}/sign-in")
    def sign_in(provider: str) -> dict[str, Any]:
        """Open the provider CLI's browser sign-in; poll GET /api/model-accounts to see it land."""
        try:
            return {"provider": accounts.sign_in(provider)}
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SignInUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/model-accounts/{provider}/sign-in/finish")
    def finish_sign_in(provider: str, body: CodeRequest) -> dict[str, Any]:
        """Claude: the code its sign-in page showed, exchanged for tokens kept in the Keychain."""
        try:
            return {"provider": accounts.finish_sign_in(provider, body.code)}
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SignInUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeychainError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/model-accounts/{provider}/install")
    def install(provider: str) -> dict[str, Any]:
        """Make the provider's CLI available (link the ChatGPT app's copy, or install it in the
        background); poll GET /api/model-accounts while the row reports `installing`."""
        try:
            return {"provider": accounts.install(provider)}
        except UnknownProvider as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SignInUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Couldn't set Codex up: {exc}") from exc
