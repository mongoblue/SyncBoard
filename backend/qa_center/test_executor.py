"""
旧版 API 用例执行器。

使用 django.test.Client 发送请求（仅能打项目内部 Django URL）。

此 executor 当前仍被以下路径使用：
  - views_api_test.py:ApiTestCaseBatchRunView（批量运行旧版用例）
  - views_devops.py:execute_api_test_cases（DevOps 自动化任务执行）

与新版执行器（api_auto_executor）的差异：
  - 此路不走 unittest.TestCase，只是工具函数
  - 断言先检查 has_status_code_assertion，不重复追加
  - 结果写入 ApiTestResult + TestRunCaseResult（双写）

"""
import json
import logging
import time
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class AssertionResult:
    """断言结果"""
    assertion_type: str  # status_code, json_path, header, response_time
    field: str
    operator: str
    expected_value: Any
    actual_value: Any
    passed: bool
    message: str


@dataclass
class CaseExecutionResult:
    """单个用例执行结果"""
    case_id: int
    case_name: str
    passed: bool
    status_code: int
    response_time_ms: int
    message: str
    
    # 请求信息
    request_method: str
    request_url: str
    request_headers: Dict
    request_body: Any
    
    # 响应信息
    response_headers: Dict
    response_body: str
    
    # 断言结果
    assertions: List[AssertionResult]
    
    # 预期结果
    expected_status: Optional[int]
    expected_response: Optional[str]


def evaluate_assertion(
    assertion_type: str,
    field: str,
    operator: str,
    expected_value: Any,
    actual_response: requests.Response,
    response_body_parsed: Any,
    response_time_ms: int
) -> AssertionResult:
    """评估单个断言"""
    actual_value = None
    passed = False
    message = ""
    
    try:
        if assertion_type == 'status_code':
            actual_value = actual_response.status_code if actual_response else None
            # 确保类型一致 - 都转换为整数
            try:
                actual_value_int = int(actual_value) if actual_value is not None else None
                expected_value_int = int(expected_value) if expected_value is not None else None
            except:
                actual_value_int = actual_value
                expected_value_int = expected_value
            
            logger.debug(
                "状态码断言 - actual_value: %s (type: %s), expected_value: %s (type: %s)",
                actual_value_int, type(actual_value_int).__name__,
                expected_value_int, type(expected_value_int).__name__
            )
            logger.debug("比较结果: %s == %s -> %s", actual_value_int, expected_value_int, actual_value_int == expected_value_int)

            if operator in ('equals', '=='):
                passed = actual_value_int == expected_value_int
                logger.debug("equals 比较: %s == %s = %s", actual_value_int, expected_value_int, passed)
            elif operator in ('not_equals', '!='):
                passed = actual_value_int != expected_value_int
            elif operator in ('greater_than', '>'):
                passed = actual_value_int > expected_value_int
            elif operator in ('less_than', '<'):
                passed = actual_value_int < expected_value_int
            else:
                logger.debug("未知运算符: %s", operator)
            logger.debug("比较后 passed: %s", passed)
            message = f"状态码 {actual_value} {'==' if passed else '!='} {expected_value}"
            # 使用转换后的值作为 expected_value 返回
            expected_value = expected_value_int
            
        elif assertion_type == 'response_time':
            actual_value = response_time_ms
            if operator == 'less_than':
                passed = actual_value < expected_value
            elif operator == 'greater_than':
                passed = actual_value > expected_value
            message = f"响应时间 {actual_value}ms {'<' if passed else '>='} {expected_value}ms"
            
        elif assertion_type == 'json_path':
            # 简单的 JSON path 解析 (支持点号分隔，如 data.user.name)
            keys = field.split('.')
            value = response_body_parsed
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break
            actual_value = value
            
            if operator == 'equals':
                passed = actual_value == expected_value
            elif operator == 'not_equals':
                passed = actual_value != expected_value
            elif operator == 'contains':
                passed = expected_value in str(actual_value) if actual_value else False
            elif operator == 'exists':
                passed = actual_value is not None
            
            message = f"字段 {field} = {actual_value} {'满足' if passed else '不满足'} 条件"
            
        elif assertion_type == 'header':
            actual_value = actual_response.headers.get(field)
            if operator == 'equals':
                passed = actual_value == expected_value
            elif operator == 'contains':
                passed = expected_value in str(actual_value) if actual_value else False
            elif operator == 'exists':
                passed = actual_value is not None
            message = f"Header {field} = {actual_value} {'满足' if passed else '不满足'} 条件"
            
    except Exception as e:
        message = f"断言执行异常: {str(e)}"
        passed = False
    
    print(f"[DEBUG] evaluate_assertion 返回前 - passed: {passed}, actual_value: {actual_value}, expected_value: {expected_value}")
    
    return AssertionResult(
        assertion_type=assertion_type,
        field=field,
        operator=operator,
        expected_value=expected_value,
        actual_value=actual_value,
        passed=passed,
        message=message
    )


def execute_api_test_case(test_case, session=None) -> CaseExecutionResult:
    """
    执行单个 API 测试用例（真实 HTTP 请求）
    :param test_case: ApiTestCase 模型实例
    :param session: requests.Session 对象，用于保持 cookie
    :return: 执行结果
    """
    from .models import ApiTestResult
    
    # 准备请求
    url = test_case.url
    method = test_case.method.upper()
    headers = test_case.headers or {}
    body = test_case.body
    
    # 处理 headers
    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except:
            headers = {}
    
    # 处理 body
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except:
            pass
    
    request_headers = headers
    request_body = body
    
    # 发送请求
    start_time = time.time()
    response = None
    error_message = None
    
    # 使用 session 或直接使用 requests
    req = session if session else requests
    
    try:
        if method == 'GET':
            response = req.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            response = req.post(url, json=body, headers=headers, timeout=30)
        elif method == 'PUT':
            response = req.put(url, json=body, headers=headers, timeout=30)
        elif method == 'PATCH':
            response = req.patch(url, json=body, headers=headers, timeout=30)
        elif method == 'DELETE':
            response = req.delete(url, headers=headers, timeout=30)
        else:
            response = req.get(url, headers=headers, timeout=30)
            
    except requests.exceptions.Timeout:
        error_message = "请求超时 (>30s)"
    except requests.exceptions.ConnectionError:
        error_message = "连接失败，请检查URL是否正确"
    except requests.exceptions.RequestException as e:
        error_message = f"请求异常: {str(e)}"
    except Exception as e:
        error_message = f"执行异常: {str(e)}"
    
    response_time_ms = int((time.time() - start_time) * 1000)
    
    # 解析响应
    if response:
        status_code = response.status_code
        try:
            response_body = response.text
            response_body_parsed = response.json()
        except:
            response_body = response.text
            response_body_parsed = None
        response_headers = dict(response.headers)
    else:
        status_code = 0
        response_body = ""
        response_body_parsed = None
        response_headers = {}
    
    # 执行断言
    assertions = []
    
    # 调试信息
    print(f"[DEBUG] 执行断言 - 响应状态码: {status_code}, response对象: {response is not None}")
    
    # 1. 解析并执行用例中的断言配置（从 expected_response 中获取）
    expected_response = test_case.expected_response or {}
    if isinstance(expected_response, dict):
        assertions_config = expected_response.get('assertions', [])
    else:
        assertions_config = []
    if isinstance(assertions_config, str):
        try:
            assertions_config = json.loads(assertions_config)
        except:
            assertions_config = []
    
    print(f"[DEBUG] 断言配置: {assertions_config}")
    
    # 检查 assertions 中是否已包含状态码断言
    has_status_code_assertion = any(
        a.get('type') == 'status_code' for a in assertions_config if isinstance(a, dict)
    )
    print(f"[DEBUG] has_status_code_assertion: {has_status_code_assertion}, expected_status: {test_case.expected_status}")
    
    # 2. 如果 assertions 中没有状态码断言，但 expected_status 有值，则添加状态码断言
    if not has_status_code_assertion and test_case.expected_status is not None:
        print(f"[DEBUG] 添加 expected_status 断言: {test_case.expected_status}")
        assertions.append(evaluate_assertion(
            'status_code', '', 'equals',
            test_case.expected_status,
            response, response_body_parsed, response_time_ms
        ))
    
    # 3. 执行 assertions 中的断言
    for assertion in assertions_config:
        if isinstance(assertion, dict):
            print(f"[DEBUG] 添加断言: {assertion}")
            # 兼容不同的字段名：expected_value 或 value
            expected_value = assertion.get('expected_value')
            if expected_value is None and 'value' in assertion:
                expected_value = assertion['value']
            # 将字符串类型的数值转换为整数
            if assertion.get('type') == 'status_code' and isinstance(expected_value, str):
                try:
                    expected_value = int(expected_value)
                except:
                    pass
            assertions.append(evaluate_assertion(
                assertion.get('type', 'status_code'),
                assertion.get('field', ''),
                assertion.get('operator', 'equals'),
                expected_value,
                response, response_body_parsed, response_time_ms
            ))
    
    # 确定最终通过状态
    print(f"[DEBUG] 断言列表: {[(a.assertion_type, a.expected_value, a.actual_value, a.passed) for a in assertions]}")
    if error_message:
        passed = False
        message = error_message
        print(f"[DEBUG] 有错误消息: {error_message}")
    elif assertions:
        passed = all(a.passed for a in assertions)
        failed_assertions = [a for a in assertions if not a.passed]
        print(f"[DEBUG] 断言结果: passed={passed}, 失败断言数={len(failed_assertions)}")
        if failed_assertions:
            message = f"断言失败: {', '.join([a.message for a in failed_assertions])}"
        else:
            message = "所有断言通过"
    else:
        # 没有断言时，根据状态码判断
        passed = 200 <= status_code < 300
        message = f"状态码: {status_code}"
        print(f"[DEBUG] 无断言，根据状态码判断: {passed}")
    
    # 保存结果到数据库
    try:
        ApiTestResult.objects.create(
            test_case=test_case,
            status_code=status_code,
            response_body=response_body[:10000] if response_body else "",
            response_headers=response_headers,
            response_time_ms=response_time_ms,
            passed=passed,
            executed_by=None
        )

        from .models import TestResult
        import json

        # 构建断言结果列表
        assertion_results_list = []
        for a in assertions:
            assertion_results_list.append({
                'type': a.assertion_type,
                'field': a.field,
                'operator': a.operator,
                'expected_value': a.expected_value,
                'actual_value': a.actual_value,
                'passed': a.passed,
                'message': a.message
            })

        # 构建完整的执行日志
        execution_log = {
            'summary': {
                'total': 1,
                'passed': 1 if passed else 0,
                'failed': 0 if passed else 1,
                'pass_rate': 100 if passed else 0
            },
            'results': [{
                'case_id': test_case.id,
                'case_name': test_case.name,
                'type': 'api',
                'passed': passed,
                'response_time_ms': response_time_ms,
                'message': message,
                'request': {
                    'method': method,
                    'url': url,
                    'headers': request_headers,
                    'body': request_body
                },
                'response': {
                    'status_code': status_code,
                    'headers': response_headers,
                    'body': response_body[:2000] if response_body else ''
                },
                'assertions': assertion_results_list
            }]
        }

        TestResult.objects.create(
            test_type='api',
            name=test_case.name,
            source='devops',
            project=test_case.project,
            api_test_case=test_case,
            status='passed' if passed else 'failed',
            executed_by=None,
            duration_ms=response_time_ms,
            actual_result=response_body[:2000] if response_body else '',
            error_message=error_message if error_message else '',
            test_log=json.dumps(execution_log, ensure_ascii=False, default=str),
        )
    except Exception as e:
        print(f"保存测试结果失败: {e}")
    
    return CaseExecutionResult(
        case_id=test_case.id,
        case_name=test_case.name,
        passed=passed,
        status_code=status_code,
        response_time_ms=response_time_ms,
        message=message,
        request_method=method,
        request_url=url,
        request_headers=request_headers,
        request_body=request_body,
        response_headers=response_headers,
        response_body=response_body[:2000] if response_body else "",  # 限制长度
        assertions=assertions,
        expected_status=test_case.expected_status,
        expected_response=getattr(test_case, 'expected_response', None)
    )


def execute_api_test_cases(case_ids: List[int]) -> List[Dict]:
    """
    批量执行 API 测试用例
    :param case_ids: 测试用例ID列表
    :return: 执行结果列表（可序列化的字典）
    """
    from .models import ApiTestCase
    
    results = []
    
    # 使用 session 保持 cookie，支持登录态
    session = requests.Session()
    
    for case_id in case_ids:
        try:
            test_case = ApiTestCase.objects.get(id=case_id)
            result = execute_api_test_case(test_case, session)
            
            # 转换为可序列化的字典
            result_dict = {
                'case_id': result.case_id,
                'case_name': result.case_name,
                'passed': result.passed,
                'status_code': result.status_code,
                'response_time_ms': result.response_time_ms,
                'message': result.message,
                'request': {
                    'method': result.request_method,
                    'url': result.request_url,
                    'headers': result.request_headers,
                    'body': result.request_body
                },
                'response': {
                    'status_code': result.status_code,
                    'headers': result.response_headers,
                    'body': result.response_body
                },
                'assertions': [
                    {
                        'type': a.assertion_type,
                        'field': a.field,
                        'operator': a.operator,
                        'expected_value': a.expected_value,
                        'actual_value': a.actual_value,
                        'passed': a.passed,
                        'message': a.message
                    }
                    for a in result.assertions
                ],
                'expected_status': result.expected_status,
                'expected_response': result.expected_response
            }
            results.append(result_dict)
            
        except ApiTestCase.DoesNotExist:
            results.append({
                'case_id': case_id,
                'case_name': '未知用例',
                'passed': False,
                'status_code': 0,
                'response_time_ms': 0,
                'message': '测试用例不存在',
                'request': {},
                'response': {},
                'assertions': []
            })
    
    return results
