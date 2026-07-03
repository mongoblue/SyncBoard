from __future__ import annotations

import json
from types import SimpleNamespace
from dataclasses import asdict
from typing import Any, Dict, Iterable, List
from urllib.parse import urlencode

from qa_center import extractors as ex_engine
from qa_center import request_builder as rb
from qa_center import template_engine as te
from qa_center import unified_assertions as ua

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


REQUEST_BODY_LIMIT = 256 * 1024
RESPONSE_BODY_LIMIT = 512 * 1024
CURL_LIMIT = 64 * 1024
EXTRACTED_VALUE_LIMIT = 4 * 1024
ASSERTION_VALUE_LIMIT = 16 * 1024

TRANSPORT_FAILURE_MAP = {
    "timeout": (FailureType.TIMEOUT, "timeout", "timeout"),
    "ssrf_blocked": (FailureType.CONFIG_ERROR, "ssrf_blocked", "ssrf_blocked"),
    "connection_error": (FailureType.NETWORK_ERROR, "network_error", "network_error"),
    "ssl_error": (FailureType.SSL_ERROR, "ssl_error", "ssl_error"),
    "transport_error": (FailureType.NETWORK_ERROR, "network_error", "network_error"),
}


class UnifiedApiRunner:
    def __init__(self, *, transport) -> None:
        self.transport = transport

    def run(
        self,
        definition: ApiExecutionDefinition,
        context: ApiExecutionContext,
    ) -> ApiCaseExecutionResult:
        redactor = SecretRedactor(
            secret_names=context.secret_names,
            secret_values=context.secret_values,
        )

        report, resolved_variables = self._build_variable_pool(context, redactor)
        warnings = list(report.warnings)
        unresolved_request_bits: List[str] = []
        curl_envelope = None

        try:
            prepared_request = self._prepare_request(
                definition=definition,
                context=context,
                variables=resolved_variables,
            )

            unresolved_request_bits = self._collect_unresolved_from_request(prepared_request)
            if unresolved_request_bits:
                report.unresolved_variables = sorted(set(report.unresolved_variables + unresolved_request_bits))
                warning = {
                    "warning_code": "unresolved_variables_blocked",
                    "variables": sorted(set(unresolved_request_bits)),
                }
                warnings.append(warning)
                report.warnings.append(warning)
                persistable = PersistableResult(
                    trace_id=context.trace_id,
                    raw_status="unresolved_variables",
                    error_code="unresolved_variables",
                    error_message="Unresolved variables blocked request execution",
                    request_snapshot=self._build_request_snapshot(
                        definition=definition,
                        request=prepared_request,
                        redactor=redactor,
                    ),
                    response_snapshot={},
                    assertion_details=[],
                    extracted_variables_preview={},
                    curl=None,
                    metadata={
                        **(definition.metadata or {}),
                        "variable_resolution_report": self._redacted_report(report, redactor),
                    },
                    warnings=warnings,
                )
                return ApiCaseExecutionResult(
                    status="unresolved_variables",
                    error_code="unresolved_variables",
                    error_message="Unresolved variables blocked request execution",
                    trace_id=context.trace_id,
                    runtime_outputs=RuntimeOutputs(extracted_variables={}, eligible_for_chain=False),
                    persistable_result=persistable,
                    failure_type=FailureType.CONFIG_ERROR,
                    summary="存在未解析的变量，请求未发送",
                )

            curl_envelope = redactor.make_text_envelope(
                self._build_curl(prepared_request),
                limit_bytes=CURL_LIMIT,
                content_type="text/plain",
            )
            request_snapshot = self._build_request_snapshot(
                definition=definition,
                request=prepared_request,
                redactor=redactor,
            )

            base_url = (resolved_variables or {}).get("base_url") or ""
            if not base_url and prepared_request.rendered_url.startswith("/"):
                config_msg = (
                    "用例使用了相对 URL（{}），但环境未配置 base_url。"
                    "请为用例绑定一个含 base_url 的 environment，或在 url 中使用完整地址。"
                ).format(prepared_request.rendered_url)
                persistable = PersistableResult(
                    trace_id=context.trace_id,
                    raw_status="config_error",
                    error_code="missing_base_url",
                    error_message=redactor.redact_text(config_msg).value,
                    request_snapshot=request_snapshot,
                    response_snapshot={},
                    assertion_details=[],
                    extracted_variables_preview={},
                    curl=curl_envelope,
                    metadata={
                        **(definition.metadata or {}),
                        "variable_resolution_report": self._redacted_report(report, redactor),
                    },
                    warnings=warnings,
                    failure_type=FailureType.CONFIG_ERROR,
                    summary="相对 URL 但未配置 base_url",
                    diagnosis={
                        "framework": "config",
                        "title": "缺少 base_url",
                        "root_cause": config_msg,
                        "suggested_fixes": [
                            "为用例绑定一个含 base_url 的 environment，例如 http://127.0.0.1:8000",
                            "或在用例 url 中直接使用完整 URL",
                            "确认环境变量 {{base_url}} 已正确定义",
                        ],
                        "message": "missing_base_url",
                    },
                )
                return ApiCaseExecutionResult(
                    status="config_error",
                    error_code="missing_base_url",
                    error_message=config_msg,
                    trace_id=context.trace_id,
                    runtime_outputs=RuntimeOutputs(extracted_variables={}, eligible_for_chain=False),
                    persistable_result=persistable,
                    failure_type=FailureType.CONFIG_ERROR,
                    summary="相对 URL 但未配置 base_url",
                    diagnosis=persistable.diagnosis,
                )

            response = self.transport.send(prepared_request, context)
            if response.error_type:
                failure_type, status, error_code = TRANSPORT_FAILURE_MAP.get(
                    response.error_type,
                    (FailureType.UNKNOWN_ERROR, "request_error", "request_error"),
                )
                response_snapshot = self._build_response_snapshot(response, redactor)
                persistable = PersistableResult(
                    trace_id=context.trace_id,
                    raw_status=status,
                    error_code=error_code,
                    error_message=redactor.redact_text(response.error_message or "").value,
                    request_snapshot=request_snapshot,
                    response_snapshot=response_snapshot,
                    assertion_details=[],
                    extracted_variables_preview={},
                    curl=curl_envelope,
                    metadata={
                        **(definition.metadata or {}),
                        "variable_resolution_report": self._redacted_report(report, redactor),
                    },
                    warnings=warnings,
                    failure_type=failure_type,
                    summary="请求传输失败：{}".format(error_code),
                )
                return ApiCaseExecutionResult(
                    status=status,
                    error_code=error_code,
                    error_message=response.error_message or "",
                    trace_id=context.trace_id,
                    runtime_outputs=RuntimeOutputs(extracted_variables={}, eligible_for_chain=False),
                    persistable_result=persistable,
                    failure_type=failure_type,
                    summary=persistable.summary,
                )

            response_snapshot = self._build_response_snapshot(response, redactor)

            framework_diag = classify_framework_error(response_snapshot, response)
            if framework_diag is not None:
                diag_dict = framework_diag.to_dict()
                persistable = PersistableResult(
                    trace_id=context.trace_id,
                    raw_status="framework_error",
                    error_code="framework_error",
                    error_message=redactor.redact_text(framework_diag.message or framework_diag.title).value,
                    request_snapshot=request_snapshot,
                    response_snapshot=response_snapshot,
                    assertion_details=[],
                    extracted_variables_preview={},
                    curl=curl_envelope,
                    metadata={
                        **(definition.metadata or {}),
                        "variable_resolution_report": self._redacted_report(report, redactor),
                    },
                    warnings=warnings,
                    failure_type=FailureType.FRAMEWORK_ERROR,
                    summary=framework_diag.title,
                    diagnosis=diag_dict,
                )
                return ApiCaseExecutionResult(
                    status="framework_error",
                    error_code="framework_error",
                    error_message=framework_diag.message or framework_diag.title,
                    trace_id=context.trace_id,
                    runtime_outputs=RuntimeOutputs(extracted_variables={}, eligible_for_chain=False),
                    persistable_result=persistable,
                    failure_type=FailureType.FRAMEWORK_ERROR,
                    summary=framework_diag.title,
                    diagnosis=diag_dict,
                )

            assertion_details = self._run_assertions(definition.assertions, response, redactor)
            all_passed = not assertion_details or all(item["passed"] for item in assertion_details)
            if all_passed:
                status = "passed"
                failure_type = FailureType.PASSED
                summary = "断言全部通过"
            else:
                status = "assertion_failed"
                failure_type = FailureType.ASSERTION_FAILED
                summary = "断言失败"

            extracted = self._run_extractors(definition.extractors, response)
            preview = {
                name: redactor.make_text_envelope(
                    value,
                    limit_bytes=EXTRACTED_VALUE_LIMIT,
                    content_type="application/json",
                )
                for name, value in extracted.items()
            }

            persistable = PersistableResult(
                trace_id=context.trace_id,
                raw_status=status,
                error_code="",
                error_message="",
                request_snapshot=request_snapshot,
                response_snapshot=response_snapshot,
                assertion_details=assertion_details,
                extracted_variables_preview=preview,
                curl=curl_envelope,
                metadata={
                    **(definition.metadata or {}),
                    "variable_resolution_report": self._redacted_report(report, redactor),
                },
                warnings=warnings,
                failure_type=failure_type,
                summary=summary,
            )
            return ApiCaseExecutionResult(
                status=status,
                error_code="",
                error_message="",
                trace_id=context.trace_id,
                runtime_outputs=RuntimeOutputs(
                    extracted_variables=extracted,
                    eligible_for_chain=(status == "passed"),
                ),
                persistable_result=persistable,
                failure_type=failure_type,
                summary=summary,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            request_snapshot = {}
            if "prepared_request" in locals():
                request_snapshot = self._build_request_snapshot(
                    definition=definition,
                    request=prepared_request,
                    redactor=redactor,
                )
            persistable = PersistableResult(
                trace_id=context.trace_id,
                raw_status="internal_error",
                error_code="internal_error",
                error_message=redactor.redact_text(str(exc)).value,
                request_snapshot=request_snapshot,
                response_snapshot={},
                assertion_details=[],
                extracted_variables_preview={},
                curl=curl_envelope,
                metadata={
                    "variable_resolution_report": self._redacted_report(report, redactor),
                },
                warnings=warnings,
                failure_type=FailureType.UNKNOWN_ERROR,
                summary="执行器内部异常",
            )
            return ApiCaseExecutionResult(
                status="internal_error",
                error_code="internal_error",
                error_message=str(exc),
                trace_id=context.trace_id,
                runtime_outputs=RuntimeOutputs(extracted_variables={}, eligible_for_chain=False),
                persistable_result=persistable,
                failure_type=FailureType.UNKNOWN_ERROR,
                summary="执行器内部异常",
            )

    @staticmethod
    def _classify_http_failure(
        status_code: int,
        headers: Any,
        body: str,
    ) -> FailureType:
        if status_code == 0:
            return FailureType.UNKNOWN_ERROR
        if status_code in (401, 403):
            return FailureType.AUTH_ERROR
        if 500 <= status_code < 600:
            return FailureType.SERVER_ERROR
        if 400 <= status_code < 500:
            return FailureType.UNKNOWN_ERROR
        return FailureType.PASSED

    def _build_variable_pool(
        self,
        context: ApiExecutionContext,
        redactor: SecretRedactor,
    ) -> tuple[VariableResolutionReport, Dict[str, Any]]:
        merged: Dict[str, Any] = {}
        sources: Dict[str, str] = {}
        report = VariableResolutionReport()
        warnings: List[Dict[str, Any]] = []

        layers = [
            ("system_vars", context.system_vars),
            ("global_vars", context.global_vars),
            ("environment_vars", context.environment_vars),
            ("run_overrides", context.run_overrides),
            ("chain_vars", context.chain_vars),
        ]

        for source_name, payload in layers:
            for key, value in (payload or {}).items():
                if (
                    key in context.locked_variables
                    and key in merged
                    and merged[key] != value
                ):
                    preview = redactor.make_text_envelope(value, limit_bytes=256)
                    warning = {
                        "warning_code": "locked_variable_override_ignored",
                        "variable_name": key,
                        "source": source_name,
                        "ignored_value_preview": preview["preview"],
                    }
                    warnings.append(warning)
                    report.locked_override_attempts.append(warning)
                    continue

                if key in merged and merged[key] != value:
                    report.shadowed_variables.append(
                        {
                            "variable_name": key,
                            "previous_source": sources[key],
                            "current_source": source_name,
                        }
                    )
                merged[key] = value
                sources[key] = source_name

        report.resolved_variables = redactor.redact_value(merged).value
        report.warnings = warnings
        return report, merged

    def _prepare_request(
        self,
        *,
        definition: ApiExecutionDefinition,
        context: ApiExecutionContext,
        variables: Dict[str, Any],
    ) -> ApiPreparedRequest:
        rendered_url = te.resolve_url(definition.url_template, variables)
        headers = te.render_value(dict(definition.headers_template or {}), variables)
        query_params = rb.normalize_query_params(definition.query_params_template, variables)
        cookies = te.render_value(definition.cookies_template or {}, variables) if definition.cookies_template else None
        auth = te.render_value(definition.auth_template, variables) if definition.auth_template else None

        body = None
        files = None
        body_mode = definition.body_mode or "none"

        if body_mode == "json":
            body = te.render_value(definition.body_template, variables)
        elif body_mode == "form":
            body = rb.normalize_query_params(definition.body_template, variables)
        elif body_mode == "raw":
            if isinstance(definition.body_template, str):
                body = te.render_string(definition.body_template, variables)
            else:
                body = te.render_value(definition.body_template, variables)
        elif body_mode == "multipart":
            body = rb.normalize_query_params(definition.body_template, variables)
            files = [
                ApiPreparedFile(
                    field_name=name,
                    filename=filename,
                    content_bytes=content_bytes,
                    content_type=content_type,
                    size_bytes=len(content_bytes),
                    truncated=False,
                )
                for name, (filename, content_bytes, content_type)
                in (rb.build_file_tuples(definition.files_template, variables) or [])
            ]
        elif body_mode == "binary":
            body = definition.body_template
        else:
            body = None

        return ApiPreparedRequest(
            method=definition.method,
            rendered_url=rendered_url,
            headers=headers,
            query_params=query_params,
            body=body,
            body_mode=body_mode,
            files=files,
            cookies=cookies,
            auth=auth,
            timeout=definition.timeout_seconds,
            allow_redirects=definition.allow_redirects,
            trace_id=context.trace_id,
            metadata={"source_type": definition.source_type, "source_id": definition.source_id},
        )

    def _collect_unresolved_from_request(self, request: ApiPreparedRequest) -> List[str]:
        return sorted(
            set(
                self._find_unresolved(request.rendered_url)
                + self._find_unresolved(request.headers)
                + self._find_unresolved(request.query_params)
                + self._find_unresolved(request.body)
                + self._find_unresolved(request.cookies)
                + self._find_unresolved(request.auth)
            )
        )

    def _find_unresolved(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return te.find_unresolved(value)
        if isinstance(value, dict):
            out: List[str] = []
            for key, inner in value.items():
                out.extend(self._find_unresolved(key))
                out.extend(self._find_unresolved(inner))
            return out
        if isinstance(value, (list, tuple)):
            out: List[str] = []
            for inner in value:
                out.extend(self._find_unresolved(inner))
            return out
        return []

    def _build_request_snapshot(
        self,
        *,
        definition: ApiExecutionDefinition,
        request: ApiPreparedRequest,
        redactor: SecretRedactor,
    ) -> Dict[str, Any]:
        auth_snapshot = None
        if request.auth:
            if isinstance(request.auth, dict):
                auth_type = request.auth.get("auth_type") or request.auth.get("type") or "custom"
            else:
                auth_type = "custom"
            auth_snapshot = {"auth_type": auth_type, "redacted": True}

        files_summary = []
        for file_item in request.files or []:
            files_summary.append(
                {
                    "field_name": file_item.field_name,
                    "filename": file_item.filename,
                    "content_type": file_item.content_type,
                    "size_bytes": file_item.size_bytes,
                    "truncated": file_item.truncated,
                }
            )

        return {
            "snapshot_schema_version": 1,
            "rendered_url": redactor.redact_text(request.rendered_url).value,
            "url_template": redactor.redact_text(definition.url_template).value,
            "headers": redactor.redact_value(request.headers).value,
            "query_params": redactor.redact_value(request.query_params).value,
            "cookies": redactor.redact_value(request.cookies).value,
            "auth": auth_snapshot,
            "body_mode": request.body_mode,
            "body": redactor.make_text_envelope(
                request.body,
                limit_bytes=REQUEST_BODY_LIMIT,
                content_type="application/json" if request.body_mode == "json" else "text/plain",
            ),
            "files": files_summary,
            "timeout": request.timeout,
            "allow_redirects": request.allow_redirects,
            "trace_id": request.trace_id,
        }

    def _build_response_snapshot(
        self,
        response: TransportResponse,
        redactor: SecretRedactor,
    ) -> Dict[str, Any]:
        content_type = ""
        if isinstance(response.headers, dict):
            for key, value in response.headers.items():
                if str(key).lower() == "content-type":
                    content_type = str(value)
                    break
        is_binary = self._is_binary_content_type(content_type)
        if is_binary:
            body_envelope = redactor.make_binary_envelope(
                response.body_bytes or b"",
                content_type=content_type or "application/octet-stream",
            )
        else:
            body_envelope = redactor.make_text_envelope(
                response.text,
                limit_bytes=RESPONSE_BODY_LIMIT,
                content_type=content_type or "text/plain",
            )
        return {
            "snapshot_schema_version": 1,
            "status_code": response.status_code,
            "headers": redactor.redact_value(response.headers).value,
            "cookies": redactor.redact_value(response.cookies).value,
            "content_type": content_type or None,
            "content_encoding": None,
            "body": body_envelope,
            "body_size_raw": len(response.body_bytes or b""),
            "body_size_decoded": len((response.text or "").encode("utf-8")),
            "final_url": redactor.redact_text(response.final_url).value if response.final_url else "",
            "redirect_chain": redactor.redact_value(response.redirect_chain).value,
            "elapsed_ms": response.elapsed_ms,
        }

    @staticmethod
    def _is_binary_content_type(content_type: str) -> bool:
        if not content_type:
            return False
        lowered = content_type.lower()
        textual_prefixes = (
            "text/",
            "application/json",
            "application/xml",
            "application/javascript",
            "application/x-www-form-urlencoded",
        )
        return not lowered.startswith(textual_prefixes)

    def _build_curl(self, request: ApiPreparedRequest) -> str:
        query = ""
        if request.query_params:
            query = "?" + urlencode(request.query_params, doseq=True)

        parts = ["curl", "-X", request.method.upper(), f"'{request.rendered_url}{query}'"]
        for key, value in (request.headers or {}).items():
            parts.extend(["-H", f"'{key}: {value}'"])
        if request.cookies:
            cookie_text = "; ".join(f"{key}={value}" for key, value in request.cookies.items())
            parts.extend(["-H", f"'Cookie: {cookie_text}'"])
        if request.body_mode == "json" and request.body is not None:
            parts.extend(["--data-raw", f"'{json.dumps(request.body, ensure_ascii=False)}'"])
        elif request.body_mode == "form" and request.body:
            encoded = urlencode(request.body, doseq=True)
            parts.extend(["--data-raw", f"'{encoded}'"])
        elif request.body_mode == "raw" and request.body is not None:
            parts.extend(["--data-raw", f"'{request.body}'"])
        return " ".join(parts)

    def _run_assertions(
        self,
        assertions: Iterable[Any],
        response: TransportResponse,
        redactor: SecretRedactor,
    ) -> List[Dict[str, Any]]:
        ctx = ua.ResponseContext.from_raw(
            status_code=response.status_code,
            response_body=response.text,
            response_headers=response.headers,
            response_time_ms=response.elapsed_ms,
        )
        results = ua.run_assertions(assertions, ctx)
        normalized: List[Dict[str, Any]] = []
        for item in results:
            transformed = dict(item)
            transformed["actual_value"] = redactor.make_text_envelope(
                item.get("actual_value"),
                limit_bytes=ASSERTION_VALUE_LIMIT,
                content_type="application/json",
            )
            transformed["expected_value"] = redactor.make_text_envelope(
                item.get("expected_value"),
                limit_bytes=ASSERTION_VALUE_LIMIT,
                content_type="application/json",
            )
            transformed["error_message"] = redactor.redact_text(
                item.get("error_message", "")
            ).value
            normalized.append(transformed)
        return normalized

    def _run_extractors(
        self,
        extractors: Iterable[Any],
        response: TransportResponse,
    ) -> Dict[str, Any]:
        response_json = None
        try:
            response_json = json.loads(response.text) if response.text else None
        except (TypeError, ValueError, json.JSONDecodeError):
            response_json = None

        normalized_extractors = [
            SimpleNamespace(**item) if isinstance(item, dict) else item
            for item in (extractors or [])
        ]

        return ex_engine.run_extractors(
            normalized_extractors,
            response_json=response_json,
            response_headers=response.headers,
            status_code=response.status_code,
            cookies=response.cookies,
            response_time_ms=response.elapsed_ms,
        )

    def _redacted_report(
        self,
        report: VariableResolutionReport,
        redactor: SecretRedactor,
    ) -> Dict[str, Any]:
        return redactor.redact_value(asdict(report)).value
