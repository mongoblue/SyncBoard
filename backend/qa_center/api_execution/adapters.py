from __future__ import annotations

from .contracts import ApiExecutionDefinition


class ApiAutoTestCaseAdapter:
    def adapt(self, case) -> ApiExecutionDefinition:
        assertions = list(case.assertions.filter(is_active=True).order_by("sort_order", "id"))
        extractors = list(case.extractors.filter(is_active=True).order_by("sort_order", "id"))
        default_policy = self._default_assertion_policy(case)
        provider_assertion = self._provider_default_status_assertion(case, default_policy)
        if provider_assertion is not None:
            assertions = [provider_assertion, *assertions]
        return ApiExecutionDefinition(
            source_type="api_auto_case",
            source_id=str(case.id),
            name=case.name,
            method=case.method,
            url_template=case.url,
            headers_template=case.headers or {},
            query_params_template=case.query_params,
            body_template=case.body or None,
            body_mode=self._body_mode(case),
            files_template=case.form_files,
            cookies_template=None,
            auth_template=None,
            timeout_seconds=case.timeout_seconds or 30,
            allow_redirects=False,
            assertions=assertions,
            extractors=extractors,
            metadata={
                "suite_id": case.suite_id,
                "case_id": case.id,
                "project_id": str(case.project_id) if case.project_id else None,
                "environment_id": case.environment_id,
                "content_type": case.content_type,
                "provider": "http",
                "expectation_type": self._expectation_type(case),
                "default_assertion_policy": default_policy,
                "expected_status": case.expected_status,
            },
        )

    @staticmethod
    def _body_mode(case) -> str:
        if case.form_files:
            return "multipart"
        if not case.body:
            return "none"
        if case.content_type == "application/json":
            return "json"
        if case.content_type == "application/x-www-form-urlencoded":
            return "form"
        return "raw"

    @staticmethod
    def _expectation_type(case) -> str:
        expected_status = case.expected_status or 200
        return "error_response" if expected_status >= 400 else "success_response"

    def _default_assertion_policy(self, case) -> str:
        return "expected_error_response" if self._expectation_type(case) == "error_response" else "success_response"

    def _provider_default_status_assertion(self, case, policy: str):
        if policy == "expected_error_response" and case.expected_status:
            return {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": case.expected_status,
                "error_message": "",
                "source": "provider_default",
                "provider": "http",
            }
        if policy == "success_response":
            return {
                "assertion_type": "status_code",
                "comparison_operator": "in",
                "expected_value": "2xx",
                "error_message": "",
                "source": "provider_default",
                "provider": "http",
            }
        return None
