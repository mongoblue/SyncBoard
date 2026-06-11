import json
import time
import logging
import requests
import pytest
from typing import Dict, List, Any, Optional
from datetime import datetime
from django.utils import timezone
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

try:
    from jsonpath import jsonpath
except ImportError:
    jsonpath = None

from .models import (
    ApiAutoTestSuite, ApiAutoTestCase, ApiAutoTestAssertion,
    ApiAutoTestResult, ApiAutoTestCaseResult
)
from .bug_utils import create_bug_from_test_failure
from . import unified_assertions as ua
from . import template_engine as te
from . import request_builder as rb


class JsonPathExtractor:
    @staticmethod
    def extract(data: Any, path: str) -> Any:
        if jsonpath is None:
            return JsonPathExtractor._manual_extract(data, path)
        result = jsonpath(data, path)
        if result is False:
            return None
        return result

    @staticmethod
    def _manual_extract(data: Any, path: str) -> Any:
        if not path:
            return data
        parts = path.replace('[', '.[').split('.')
        current = data
        for part in parts:
            if not current:
                return None
            if part.startswith('[') and part.endswith(']'):
                try:
                    index = int(part[1:-1])
                    if isinstance(current, list) and len(current) > index:
                        current = current[index]
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current


class AssertionExecutor:
    COMPARISON_OPERATORS = {
        'eq': lambda a, b: a == b,
        'ne': lambda a, b: a != b,
        'gt': lambda a, b: a > b,
        'gte': lambda a, b: a >= b,
        'lt': lambda a, b: a < b,
        'lte': lambda a, b: a <= b,
        'contains': lambda a, b: b in str(a) if a is not None else False,
        'not_contains': lambda a, b: b not in str(a) if a is not None else True,
    }

    @staticmethod
    def execute_assertion(assertion: ApiAutoTestAssertion, response_data: Any, response: requests.Response) -> Dict:
        assertion_type = assertion.assertion_type
        json_path = assertion.json_path
        expected_value = assertion.expected_value
        operator = assertion.comparison_operator or 'eq'
        error_msg = assertion.error_message or f"Assertion failed: {assertion_type}"

        result = {
            'assertion_type': assertion_type,
            'json_path': json_path,
            'expected_value': expected_value,
            'operator': operator,
            'passed': False,
            'actual_value': None,
            'error_message': ''
        }

        try:
            if assertion_type == 'status_code':
                actual_status = response.status_code
                expected_status = int(expected_value) if expected_value else response.status_code
                compare_func = AssertionExecutor.COMPARISON_OPERATORS.get(operator, AssertionExecutor.COMPARISON_OPERATORS['eq'])
                passed = compare_func(actual_status, expected_status)
                result['actual_value'] = actual_status
                result['passed'] = passed
                if not passed:
                    result['error_message'] = error_msg or f"Status code {actual_status} {operator} {expected_status}"

            elif assertion_type == 'response_time':
                actual_time = response.elapsed.total_seconds() * 1000
                expected_time = float(expected_value) if expected_value else 0
                compare_func = AssertionExecutor.COMPARISON_OPERATORS.get(operator, AssertionExecutor.COMPARISON_OPERATORS['lt'])
                passed = compare_func(actual_time, expected_time)
                result['actual_value'] = actual_time
                result['passed'] = passed
                if not passed:
                    result['error_message'] = error_msg or f"Response time {actual_time}ms {operator} {expected_time}ms"

            elif assertion_type in ('json_equals', 'json_contains', 'json_exists'):
                actual_value = JsonPathExtractor.extract(response_data, json_path) if json_path else response_data
                result['actual_value'] = actual_value

                if assertion_type == 'json_exists':
                    passed = actual_value is not None
                    if not passed:
                        result['error_message'] = error_msg or f"JSON path '{json_path}' does not exist"
                    result['passed'] = passed

                elif assertion_type == 'json_equals':
                    if actual_value is None:
                        passed = False
                        result['error_message'] = error_msg or f"JSON path '{json_path}' not found"
                    else:
                        try:
                            expected = json.loads(expected_value) if isinstance(expected_value, str) else expected_value
                        except json.JSONDecodeError:
                            expected = expected_value
                        compare_func = AssertionExecutor.COMPARISON_OPERATORS.get(operator, AssertionExecutor.COMPARISON_OPERATORS['eq'])
                        passed = compare_func(actual_value, expected)
                        if not passed:
                            result['error_message'] = error_msg or f"Value at '{json_path}' ({actual_value}) {operator} {expected}"
                    result['passed'] = passed

                elif assertion_type == 'json_contains':
                    if actual_value is None:
                        passed = False
                        result['error_message'] = error_msg or f"JSON path '{json_path}' not found"
                    else:
                        compare_func = AssertionExecutor.COMPARISON_OPERATORS.get(operator, AssertionExecutor.COMPARISON_OPERATORS['contains'])
                        passed = compare_func(str(actual_value), expected_value)
                        if not passed:
                            result['error_message'] = error_msg or f"Value at '{json_path}' does not contain '{expected_value}'"
                    result['passed'] = passed

            else:
                result['error_message'] = f"Unknown assertion type: {assertion_type}"
                result['passed'] = False

        except Exception as e:
            result['passed'] = False
            result['error_message'] = f"Assertion execution error: {str(e)}"

        return result


class ApiAutoTestExecutor:
    def __init__(self, suite_id: int, user: Optional[User] = None, *, environment_id: Optional[int] = None):
        self.suite_id = suite_id
        self.user = user
        self.suite = None
        self.test_result = None
        self.start_time = None
        self._environment_id = environment_id
        self._variables: Dict[str, Any] = {}

    def execute(self) -> ApiAutoTestResult:
        self.suite = ApiAutoTestSuite.objects.get(id=self.suite_id)
        active_cases = self.suite.test_cases.filter(is_active=True).order_by('sort_order', 'created_at')

        # M3.2: 解析变量池（环境 + 项目全局变量）
        env = te.resolve_project_environment(self.suite.project, env_id=self._environment_id)
        globals_ = te.load_project_globals(self.suite.project)
        self._variables = te.build_variable_pool(environment=env, global_vars=globals_)

        execution_name = f"{self.suite.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

        self.test_result = ApiAutoTestResult.objects.create(
            suite=self.suite,
            name=execution_name,
            status='running',
            total_cases=active_cases.count(),
            executed_by=self.user,
            started_at=timezone.now()
        )

        try:
            passed_count = 0
            failed_count = 0
            error_count = 0

            for case in active_cases:
                case_result = self._execute_case(case)
                if case_result.passed:
                    passed_count += 1
                elif case_result.error_message and 'execution' in case_result.error_message.lower():
                    error_count += 1
                else:
                    failed_count += 1

            duration = int((timezone.now() - self.test_result.started_at).total_seconds() * 1000)

            if error_count > 0:
                final_status = 'error'
            elif failed_count > 0:
                final_status = 'failed'
            else:
                final_status = 'passed'

            self.test_result.passed_cases = passed_count
            self.test_result.failed_cases = failed_count
            self.test_result.error_cases = error_count
            self.test_result.duration_ms = duration
            self.test_result.status = final_status
            self.test_result.completed_at = timezone.now()
            self.test_result.save()

            # 自动为失败用例创建 Bug 任务
            if final_status in ('failed', 'error'):
                failed_results = ApiAutoTestCaseResult.objects.filter(
                    test_result=self.test_result, passed=False
                ).select_related('case__suite__project')
                for fr in failed_results:
                    try:
                        create_bug_from_test_failure(
                            fr.case, self.test_result,
                            error_message=fr.error_message or ''
                        )
                    except Exception as bug_err:
                        logger.warning(f'[AutoBug] 创建Bug失败: {bug_err}')

        except Exception as e:
            self.test_result.status = 'error'
            self.test_result.error_message = str(e)
            self.test_result.completed_at = timezone.now()
            self.test_result.save()

        return self.test_result

    def _execute_case(self, case: ApiAutoTestCase) -> ApiAutoTestCaseResult:
        response_body = ''
        response_headers = {}
        status_code = 0
        response_time_ms = 0
        passed = False
        assertion_details = []
        error_message = ''

        try:
            headers = case.headers or {}
            if case.content_type:
                headers['Content-Type'] = case.content_type

            # M3.2: 渲染变量
            url = te.resolve_url(case.url, self._variables)
            headers = te.render_value(dict(headers), self._variables)
            raw_body = te.render_string(case.body or '', self._variables)

            # M3.4: query 参数 + 文件上传
            params = rb.normalize_query_params(case.query_params, self._variables)
            files = rb.build_file_tuples(case.form_files, self._variables)

            body = None
            if raw_body and case.method in ['POST', 'PUT', 'PATCH']:
                if case.content_type == 'application/json':
                    try:
                        body = json.loads(raw_body)
                    except json.JSONDecodeError:
                        body = raw_body
                else:
                    body = raw_body

            # M3.4: 上传文件时去掉用户写死的 Content-Type
            if files:
                headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}

            start_time = time.time()
            response = requests.request(
                method=case.method,
                url=url,
                headers=headers,
                params=params,
                json=body if isinstance(body, dict) and not files else None,
                data=body if (isinstance(body, str) or (isinstance(body, dict) and files)) else None,
                files=files,
                timeout=30
            )
            response_time_ms = int((time.time() - start_time) * 1000)

            status_code = response.status_code

            try:
                response_body = response.text
                response_data = response.json() if response.text else {}
            except json.JSONDecodeError:
                response_data = {'raw': response.text}

            response_headers = dict(response.headers)

            active_assertions = list(case.assertions.filter(is_active=True).order_by('sort_order', 'id'))
            ctx = ua.ResponseContext.from_raw(
                status_code=status_code,
                response_body=response_body,
                response_headers=response_headers,
                response_time_ms=response_time_ms,
            )
            assertion_details = ua.run_assertions(active_assertions, ctx)
            all_passed = all(r.get('passed') for r in assertion_details) if assertion_details else True

            if case.expected_status and status_code != case.expected_status:
                all_passed = False
                assertion_details.insert(0, {
                    'assertion_type': 'status_code',
                    'expected_value': case.expected_status,
                    'actual_value': status_code,
                    'passed': False,
                    'error_message': f"Expected status {case.expected_status}, got {status_code}"
                })

            passed = all_passed

        except requests.exceptions.Timeout:
            error_message = "Request timeout"
            status_code = 0
        except requests.exceptions.ConnectionError as e:
            error_message = f"Connection error: {str(e)}"
            status_code = 0
        except Exception as e:
            error_message = f"Request execution error: {str(e)}"
            status_code = 0

        case_result = ApiAutoTestCaseResult.objects.create(
            test_result=self.test_result,
            case=case,
            status_code=status_code,
            response_body=response_body[:10000],
            response_headers=response_headers,
            response_time_ms=response_time_ms,
            passed=passed,
            assertion_details=assertion_details,
            error_message=error_message
        )

        return case_result


def run_api_auto_test(suite_id: int, user: Optional[User] = None, *, environment_id: Optional[int] = None) -> ApiAutoTestResult:
    executor = ApiAutoTestExecutor(suite_id, user, environment_id=environment_id)
    return executor.execute()
