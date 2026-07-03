"""Pure API execution core for QA Center.

This package intentionally avoids importing Django models/views/tasks and keeps
the execution kernel transport-driven and side-effect free.
"""

from .contracts import (
    ApiCaseExecutionResult,
    ApiExecutionContext,
    ApiExecutionDefinition,
    ApiPreparedFile,
    ApiPreparedRequest,
    FailureType,
    PersistableResult,
    RuntimeOutputs,
    TransportResponse,
    VariableResolutionReport,
)
from .framework_errors import FrameworkDiagnosis, classify_framework_error
from .redaction import SecretRedactor
from .runtime_guard import RuntimeGuard
from .runner import UnifiedApiRunner
from .transport import (
    ApiTransport,
    MockTransport,
    RequestsTransport,
    SSRFProtectedRequestsTransport,
)

__all__ = [
    "ApiCaseExecutionResult",
    "ApiExecutionContext",
    "ApiExecutionDefinition",
    "ApiPreparedFile",
    "ApiPreparedRequest",
    "ApiTransport",
    "FailureType",
    "FrameworkDiagnosis",
    "MockTransport",
    "PersistableResult",
    "RequestsTransport",
    "RuntimeGuard",
    "RuntimeOutputs",
    "SSRFProtectedRequestsTransport",
    "SecretRedactor",
    "TransportResponse",
    "UnifiedApiRunner",
    "VariableResolutionReport",
    "classify_framework_error",
]
