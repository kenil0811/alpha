"""Alpha App SDK.

Generated App and Task code imports only this package (plus the Python standard library and any
modules its runtime profile pins). Handlers receive a Context:

    ctx.records    the App's own collections: create/get/update/correct/delete/query/aggregate
    ctx.artifacts  immutable output files with digests and provenance
    ctx.models     bounded structured model calls whose results are labelled estimates

See alpha_sdk.query for filter, sort and aggregation builders.
"""

from alpha_sdk.artifacts import ArtifactRef
from alpha_sdk.context import Context, RunInfo
from alpha_sdk.errors import (
    Conflict,
    Forbidden,
    InvalidValue,
    LimitExceeded,
    NotFound,
    OperationError,
    Unavailable,
)
from alpha_sdk.models import ModelResult
from alpha_sdk.records import Aggregation, Group, Page, Record

__version__ = "0.1.0"

__all__ = [
    "Aggregation",
    "ArtifactRef",
    "Conflict",
    "Context",
    "Forbidden",
    "Group",
    "InvalidValue",
    "LimitExceeded",
    "ModelResult",
    "NotFound",
    "OperationError",
    "Page",
    "Record",
    "RunInfo",
    "Unavailable",
    "__version__",
]
