"""The SDK is standard library only, so it keeps its own copies of the worker protocol's
version, operation names and failure codes. These tests hold each copy equal to the contract
(decision 2026-09-25-recorded-deviations, item 6)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

import alpha_sdk
from alpha_contracts.broker import (
    OPERATIONS,
    WORKER_PROTOCOL_VERSION,
    CapabilityCall,
    CapabilityErrorCode,
)
from alpha_sdk import errors
from alpha_sdk._channel import PROTOCOL_VERSION

SDK_SOURCE = Path(alpha_sdk.__file__).parent


def test_protocol_version_matches_the_contract() -> None:
    (call_version,) = get_args(CapabilityCall.model_fields["version"].annotation)
    assert PROTOCOL_VERSION == WORKER_PROTOCOL_VERSION == call_version


def sdk_operations() -> set[str]:
    """Every operation name the SDK sends: the literal first argument of each `.call(...)`."""
    found: set[str] = set()
    for path in SDK_SOURCE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "call"
                and node.args
            ):
                first = node.args[0]
                # A computed name would hide an operation from this check.
                assert isinstance(first, ast.Constant) and isinstance(first.value, str), (
                    f"{path.name}:{node.lineno} sends a computed operation name"
                )
                found.add(first.value)
    return found


def test_the_sdk_sends_exactly_the_contract_operations() -> None:
    assert sdk_operations() == set(OPERATIONS)


def test_every_contract_failure_code_reaches_handlers_unchanged() -> None:
    codes = set(get_args(CapabilityErrorCode))
    typed = {
        cls.code
        for cls in vars(errors).values()
        if isinstance(cls, type) and issubclass(cls, errors.OperationError)
    }
    assert typed <= codes, typed - codes
    for code in codes:
        raised = errors.from_reply({"code": code, "message": "m"})
        assert isinstance(raised, errors.OperationError) and raised.code == code
