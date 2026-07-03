from __future__ import annotations


def _semantic_fields(*, metadata, execution_status, failure_type):
    expectation_type = metadata.get("expectation_type") or "success_response"
    semantic_status = metadata.get("semantic_status")
    semantic_label = metadata.get("semantic_label")
    if semantic_status and semantic_label:
        return {
            "semantic_status": semantic_status,
            "semantic_label": semantic_label,
        }

    if expectation_type == "error_response":
        if execution_status == "passed":
            return {
                "semantic_status": "expected_error_matched",
                "semantic_label": "预期错误响应且匹配成功",
            }
        if failure_type == "assertion_failed" or execution_status == "assertion_failed":
            return {
                "semantic_status": "expected_error_unmatched",
                "semantic_label": "预期错误响应但未匹配",
            }
        return {
            "semantic_status": "expected_error_execution_error",
            "semantic_label": "预期错误场景执行异常",
        }

    if execution_status == "passed":
        return {
            "semantic_status": "success_response_passed",
            "semantic_label": "成功响应断言通过",
        }
    return {
        "semantic_status": "success_response_failed",
        "semantic_label": "测试失败",
    }


class ApiAutoTestCaseResultMapper:
    def create_case_result(self, *, case, test_result, execution_result):
        payload = execution_result.to_persistable_dict()
        response_snapshot = payload.get("response_snapshot") or {}
        body_envelope = (response_snapshot.get("body") or {}) if isinstance(response_snapshot, dict) else {}
        base_metadata = payload.get("metadata") or {}
        summary = payload.get("summary") or getattr(execution_result, "summary", "") or ""
        diagnosis = payload.get("diagnosis") or getattr(execution_result, "diagnosis", None)
        result_metadata = dict(base_metadata)
        if summary:
            result_metadata["summary"] = summary
        if diagnosis:
            result_metadata["diagnosis"] = diagnosis
        result_metadata.update(
            _semantic_fields(
                metadata=result_metadata,
                execution_status=execution_result.status,
                failure_type=payload.get("failure_type") or getattr(execution_result, "failure_type", "") or "",
            )
        )
        return case.case_results.model.objects.create(
            test_result=test_result,
            case=case,
            status_code=response_snapshot.get("status_code") or 0,
            response_body=body_envelope.get("preview") or "",
            response_headers=response_snapshot.get("headers") or {},
            response_time_ms=response_snapshot.get("elapsed_ms") or 0,
            passed=(execution_result.status == "passed"),
            assertion_details=payload.get("assertion_details") or [],
            error_message=payload.get("error_message") or "",
            trace_id=payload.get("trace_id") or execution_result.trace_id,
            raw_status=payload.get("raw_status") or execution_result.status,
            error_code=payload.get("error_code") or execution_result.error_code,
            request_snapshot=payload.get("request_snapshot") or {},
            response_snapshot=payload.get("response_snapshot") or {},
            curl=payload.get("curl") or {},
            extracted_variables_preview=payload.get("extracted_variables_preview") or {},
            result_metadata=result_metadata,
            failure_type=payload.get("failure_type") or getattr(execution_result, "failure_type", "") or "",
        )

    def finalize_test_result(self, *, test_result, case_result, execution_result):
        test_result.passed_cases = 1 if execution_result.status == "passed" else 0
        test_result.failed_cases = 1 if execution_result.status == "assertion_failed" else 0
        test_result.error_cases = (
            1
            if execution_result.status
            in {"timeout", "request_error", "network_error", "ssrf_blocked",
                "unresolved_variables", "internal_error", "framework_error",
                "config_error", "ssl_error", "auth_error", "server_error"}
            else 0
        )
        test_result.duration_ms = case_result.response_time_ms
        test_result.status = "passed" if execution_result.status == "passed" else (
            "failed" if execution_result.status == "assertion_failed" else "error"
        )
        test_result.error_message = case_result.error_message
        return test_result


class ApiAutoTestResultAggregator:
    def update_counts(self, *, test_result, execution_result, case_result):
        if execution_result.status == "passed":
            test_result.passed_cases += 1
        elif execution_result.status == "assertion_failed":
            test_result.failed_cases += 1
        else:
            test_result.error_cases += 1

        test_result.duration_ms = (test_result.duration_ms or 0) + (case_result.response_time_ms or 0)
        if test_result.error_cases > 0:
            test_result.status = "error"
        elif test_result.failed_cases > 0:
            test_result.status = "failed"
        else:
            test_result.status = "passed"
        if case_result.error_message:
            test_result.error_message = case_result.error_message
        return test_result
