from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional, Protocol, Sequence


class FailureType(StrEnum):
    PASSED = "passed"
    ASSERTION_FAILED = "assertion_failed"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    SSL_ERROR = "ssl_error"
    AUTH_ERROR = "auth_error"
    SERVER_ERROR = "server_error"
    FRAMEWORK_ERROR = "framework_error"
    CONFIG_ERROR = "config_error"
    SCRIPT_ERROR = "script_error"
    SCHEMA_FAILED = "schema_failed"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ApiPreparedFile:
    field_name: str
    filename: str
    content_bytes: bytes
    content_type: str
    size_bytes: int
    truncated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApiPreparedRequest:
    method: str
    rendered_url: str
    headers: Dict[str, Any]
    query_params: Optional[List[tuple[str, str]]]
    body: Any
    body_mode: str
    files: Optional[List[ApiPreparedFile]]
    cookies: Optional[Dict[str, Any]]
    auth: Any
    timeout: int
    allow_redirects: bool
    trace_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransportResponse:
    status_code: int
    headers: Dict[str, Any]
    cookies: Dict[str, Any]
    body_bytes: bytes
    text: str
    elapsed_ms: int
    final_url: str
    redirect_chain: List[Dict[str, Any]]
    error_type: Optional[str] = None
    error_message: str = ""


class ApiTransport(Protocol):
    def send(
        self,
        request: ApiPreparedRequest,
        context: "ApiExecutionContext",
    ) -> TransportResponse:
        ...


@dataclass
class ApiExecutionDefinition:
    source_type: str
    source_id: str
    name: str
    method: str
    url_template: str
    headers_template: Dict[str, Any]
    query_params_template: Any
    body_template: Any
    body_mode: str
    files_template: Any
    cookies_template: Any
    auth_template: Any
    timeout_seconds: int
    allow_redirects: bool
    assertions: Sequence[Any] = field(default_factory=list)
    extractors: Sequence[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApiExecutionContext:
    trace_id: str
    project_id: str
    environment_id: str
    system_vars: Dict[str, Any] = field(default_factory=dict)
    global_vars: Dict[str, Any] = field(default_factory=dict)
    environment_vars: Dict[str, Any] = field(default_factory=dict)
    run_overrides: Dict[str, Any] = field(default_factory=dict)
    chain_vars: Dict[str, Any] = field(default_factory=dict)
    locked_variables: set[str] = field(default_factory=set)
    secret_names: set[str] = field(default_factory=set)
    secret_values: set[str] = field(default_factory=set)
    policies: Dict[str, Any] = field(default_factory=dict)
    runtime_mode: str = "real"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VariableResolutionReport:
    resolved_variables: Dict[str, Any] = field(default_factory=dict)
    unresolved_variables: List[str] = field(default_factory=list)
    locked_override_attempts: List[Dict[str, Any]] = field(default_factory=list)
    shadowed_variables: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RuntimeOutputs:
    extracted_variables: Dict[str, Any] = field(default_factory=dict)
    eligible_for_chain: bool = False


@dataclass
class PersistableResult:
    result_schema_version: int = 1
    trace_id: str = ""
    raw_status: str = "pending"
    error_code: str = ""
    error_message: str = ""
    request_snapshot: Dict[str, Any] = field(default_factory=dict)
    response_snapshot: Dict[str, Any] = field(default_factory=dict)
    assertion_details: List[Dict[str, Any]] = field(default_factory=list)
    extracted_variables_preview: Dict[str, Any] = field(default_factory=dict)
    curl: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    failure_type: str = FailureType.UNKNOWN_ERROR
    summary: str = ""
    diagnosis: Optional[Dict[str, Any]] = None


@dataclass
class ApiCaseExecutionResult:
    status: str
    error_code: str
    error_message: str
    trace_id: str
    runtime_outputs: RuntimeOutputs
    persistable_result: PersistableResult
    failure_type: str = FailureType.UNKNOWN_ERROR
    summary: str = ""
    diagnosis: Optional[Dict[str, Any]] = None

    def to_persistable_dict(self) -> Dict[str, Any]:
        data = asdict(self.persistable_result)
        return data
