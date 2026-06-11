import time
import json
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.test import Client
from django.urls import resolve
from django.http import HttpRequest
from django.utils import timezone
from django.db.models import F
from .models import ApiTestCase, ApiTestResult, TestResult, TestRun, TestRunCaseResult
from .utils.curl import to_curl
from .serializers import (
    ApiTestCaseSerializer,
    ApiTestCaseListSerializer,
    ApiTestResultSerializer,
    ApiTestRunResponseSerializer
)
from .assertion_engine import AssertionEngine  # 保留以兼容外部 import；新代码请用 unified_assertions
from . import unified_assertions as ua
from . import template_engine as te


class ApiTestCaseViewSet(viewsets.ModelViewSet):
    """API 测试用例 ViewSet"""
    
    permission_classes = [IsAuthenticated]
    queryset = ApiTestCase.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ApiTestCaseListSerializer
        return ApiTestCaseSerializer
    
    def get_queryset(self):
        """根据项目ID筛选"""
        queryset = ApiTestCase.objects.all()
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset
    
    def perform_create(self, serializer):
        """创建时自动设置创建者"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """
        运行 API 测试用例
        POST /api/qa/api-cases/{id}/run/
        """
        test_case = self.get_object()

        # 获取运行参数（支持临时覆盖）
        override_data = request.data
        url = override_data.get('url', test_case.url)
        method = override_data.get('method', test_case.method)
        headers = override_data.get('headers', test_case.headers)
        body = override_data.get('body', test_case.body)

        # 处理 headers 和 body 的 JSON 解析
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except json.JSONDecodeError:
                return Response(
                    {'error': 'Headers JSON 格式错误'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return Response(
                    {'error': 'Body JSON 格式错误'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # M3.2: 解析项目变量池（环境 + 全局变量）。允许 override 里传 environment_id。
        environment_id = override_data.get('environment_id')
        variables = te.build_variable_pool(
            environment=te.resolve_project_environment(test_case.project, env_id=environment_id),
            global_vars=te.load_project_globals(test_case.project),
        )
        if variables:
            url = te.resolve_url(url, variables)
            headers = te.render_value(headers, variables)
            body = te.render_value(body, variables)

        # 双写: 创建 TestRun(单条也视为一次运行)。放在所有输入校验通过后，
        # 避免 400 时残留 status='running' 的孤儿 TestRun。
        test_run = TestRun.objects.create(
            project=test_case.project,
            name=f"{test_case.name} @ {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            trigger='manual',
            test_type='api',
            status='running',
            total_count=1,
            started_at=timezone.now(),
            triggered_by=request.user,
            config_snapshot={'source': 'single', 'case_id': test_case.id},
        )

        # 使用 Django Test Client 发送请求（自动携带当前用户 session）
        start_time = time.time()
        try:
            # 创建 test client 并设置 session
            client = Client()
            
            # 复制当前请求的 session 到 test client
            if request.session:
                client.cookies['sessionid'] = request.COOKIES.get('sessionid', '')
                client.cookies['csrftoken'] = request.COOKIES.get('csrftoken', '')
            
            # 准备请求头
            request_headers = headers.copy()
            if body and 'Content-Type' not in request_headers:
                request_headers['Content-Type'] = 'application/json'
            
            # 发送请求
            if method == 'GET':
                response = client.get(url, **request_headers)
            elif method == 'POST':
                response = client.post(url, data=json.dumps(body) if body else {}, content_type='application/json', **request_headers)
            elif method == 'PUT':
                response = client.put(url, data=json.dumps(body) if body else {}, content_type='application/json', **request_headers)
            elif method == 'PATCH':
                response = client.patch(url, data=json.dumps(body) if body else {}, content_type='application/json', **request_headers)
            elif method == 'DELETE':
                response = client.delete(url, **request_headers)
            elif method == 'HEAD':
                response = client.head(url, **request_headers)
            elif method == 'OPTIONS':
                response = client.options(url, **request_headers)
            else:
                # 不支持的 method：标记 TestRun 为 error 后再返回，避免孤儿。
                test_run.status = 'error'
                test_run.completed_at = timezone.now()
                test_run.duration_ms = int((time.time() - start_time) * 1000)
                test_run.save(update_fields=['status', 'completed_at', 'duration_ms'])
                return Response(
                    {'error': f'不支持的请求方法: {method}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            response_time_ms = int((time.time() - start_time) * 1000)
            status_code = response.status_code
            response_body = response.content.decode('utf-8')
            response_headers = dict(response.headers)
            
            # 执行断言 - 从 expected_response 中获取断言配置
            expected_response = test_case.expected_response or {}
            # 兼容字符串格式（AI 工具可能存储了字符串）
            if isinstance(expected_response, str):
                try:
                    expected_response = json.loads(expected_response)
                except json.JSONDecodeError:
                    expected_response = {}
            if isinstance(expected_response, dict):
                assertions = expected_response.get('assertions', [])
            elif isinstance(expected_response, list):
                assertions = expected_response  # 直接是断言数组
            else:
                assertions = []
            assertion_results = ua.run_assertions(
                assertions,
                ua.ResponseContext.from_raw(
                    status_code=status_code,
                    response_body=response_body,
                    response_headers=response_headers,
                    response_time_ms=response_time_ms,
                ),
            )

            # 变量提取(M3.3): 从响应里抽出变量,稍后挂到 assertion_results 末尾
            from . import extractors as ext
            parsed_body = None
            if response_body:
                try:
                    parsed_body = json.loads(response_body)
                except (json.JSONDecodeError, TypeError):
                    parsed_body = None
            extracted = {}
            for spec in (test_case.response_extractions or []):
                if not isinstance(spec, dict):
                    continue
                name = (spec.get('var_name') or spec.get('name') or '').strip()
                if not name:
                    continue
                value = ext.extract_value(
                    source=spec.get('source', 'body'),
                    expression=spec.get('json_path') or spec.get('expression') or '',
                    response_json=parsed_body,
                    response_headers=response_headers,
                    status_code=status_code,
                    response_time_ms=response_time_ms,
                    default=spec.get('default'),
                )
                extracted[name] = value
            extractions_summary = ext.summarize_extractions(extracted)

            # 判断测试是否通过(extractions 块不参与 passed 计算,放到后面追加)
            all_assertions_passed = all(r['passed'] for r in assertion_results) if assertion_results else True

            # 检查状态码
            expected_status = test_case.expected_status
            if expected_status is not None and expected_status > 0:
                status_passed = (status_code == expected_status)
            else:
                status_passed = (200 <= status_code < 300)

            passed = all_assertions_passed and status_passed

            # 把 extractions 块挂到 assertion_results 末尾(不影响 passed 判定)
            if extractions_summary:
                assertion_results = list(assertion_results) + [{'extractions': extractions_summary}]

            # 保存测试结果
            result = ApiTestResult.objects.create(
                test_case=test_case,
                status_code=status_code,
                response_body=response_body[:10000],
                response_headers=response_headers,
                response_time_ms=response_time_ms,
                passed=passed,
                assertion_results=assertion_results,
                executed_by=request.user
            )

            # 双写: 写 TestRunCaseResult
            request_snapshot = {
                'method': method,
                'url': url,
                'headers': headers,
                'body': body,
            }
            curl_str = to_curl(method, url, headers, body,
                               content_type=test_case.content_type or 'application/json')
            case_result = TestRunCaseResult.objects.create(
                test_run=test_run,
                case_type='api',
                sequence=1,
                api_test_case=test_case,
                status='passed' if passed else 'failed',
                duration_ms=response_time_ms,
                status_code=status_code,
                response_body=response_body[:10000],
                response_headers=response_headers,
                assertion_results=assertion_results,
                request_snapshot=request_snapshot,
                curl=curl_str,
                legacy_api_result_id=result.id,
                legacy_test_result_id=None,  # 后面 TestResult 写完后回填
                started_at=test_run.started_at,
                completed_at=timezone.now(),
            )
            # 更新 TestRun 计数与状态
            if passed:
                TestRun.objects.filter(id=test_run.id).update(
                    passed_count=F('passed_count') + 1
                )
            else:
                TestRun.objects.filter(id=test_run.id).update(
                    failed_count=F('failed_count') + 1
                )
            test_run.refresh_from_db()
            test_run.recompute_pass_rate()
            test_run.status = 'passed' if test_run.failed_count == 0 and test_run.error_count == 0 else 'failed'
            test_run.completed_at = timezone.now()
            test_run.duration_ms = response_time_ms
            # update_fields 限定字段，避免 full save 覆盖 F() 已经更新过的计数。
            test_run.save(update_fields=['status', 'completed_at', 'duration_ms', 'pass_rate'])

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
                    'message': f'状态码 {status_code} == {test_case.expected_status}' if test_case.expected_status else f'状态码 {status_code}',
                    'request': {
                        'method': method,
                        'url': url,
                        'headers': headers,
                        'body': body
                    },
                    'response': {
                        'status_code': status_code,
                        'headers': response_headers,
                        'body': response_body[:2000] if response_body else ''
                    },
                    'assertions': assertion_results
                }]
            }

            test_result = TestResult.objects.create(
                test_type='api',
                name=test_case.name,
                source='single',
                project=test_case.project,
                api_test_case=test_case,
                status='passed' if passed else 'failed',
                executed_by=request.user,
                duration_ms=response_time_ms,
                actual_result=response_body[:2000] if response_body else '',
                test_log=json.dumps(execution_log, ensure_ascii=False, default=str),
            )
            # 回填 legacy_test_result_id
            case_result.legacy_test_result_id = test_result.id
            case_result.save(update_fields=['legacy_test_result_id'])

            # 返回执行结果
            result_data = {
                'status_code': status_code,
                'response_body': response_body[:10000],
                'response_headers': response_headers,
                'response_time_ms': response_time_ms,
                'passed': passed,
                'expected_status': test_case.expected_status,
                'assertion_results': assertion_results,
                'result_id': result.id,
                'run_id': test_run.id,
                'case_result_id': case_result.id,
                'curl': curl_str,
            }
            
            return Response(result_data)
            
        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            # 执行断言（在异常情况下）- 从 expected_response 中获取断言配置
            expected_response = test_case.expected_response or {}
            if isinstance(expected_response, dict):
                assertions = expected_response.get('assertions', [])
            else:
                assertions = []
            assertion_results = ua.run_assertions(
                assertions,
                ua.ResponseContext.from_raw(
                    status_code=0, response_body='', response_headers={}, response_time_ms=response_time_ms,
                ),
            )
            result = ApiTestResult.objects.create(
                test_case=test_case,
                status_code=0,
                response_body='',
                response_headers={},
                response_time_ms=response_time_ms,
                passed=False,
                assertion_results=assertion_results,
                error_message=str(e),
                executed_by=request.user
            )

            # 双写: 异常路径也写 TestRunCaseResult。
            # 走到这里时 method/url/headers/body 都已经经过校验，是合法类型；
            # 只有 to_curl 自己可能因为 header 值类型异常抛错，单独防护。
            request_snapshot = {
                'method': method,
                'url': url,
                'headers': headers,
                'body': body,
            }
            try:
                curl_str = to_curl(method, url, headers, body,
                                   content_type=test_case.content_type or 'application/json')
            except Exception:
                curl_str = ''
            case_result = TestRunCaseResult.objects.create(
                test_run=test_run,
                case_type='api',
                sequence=1,
                api_test_case=test_case,
                status='error',
                duration_ms=response_time_ms,
                status_code=0,
                response_body='',
                response_headers={},
                assertion_results=assertion_results,
                request_snapshot=request_snapshot,
                curl=curl_str,
                error_message=str(e),
                legacy_api_result_id=result.id,
                legacy_test_result_id=None,
                started_at=test_run.started_at,
                completed_at=timezone.now(),
            )
            TestRun.objects.filter(id=test_run.id).update(
                error_count=F('error_count') + 1
            )
            test_run.refresh_from_db()
            test_run.recompute_pass_rate()
            test_run.status = 'error'
            test_run.completed_at = timezone.now()
            test_run.duration_ms = response_time_ms
            test_run.save(update_fields=['status', 'completed_at', 'duration_ms', 'pass_rate'])

            # 构建异常情况的执行日志
            error_log = {
                'summary': {
                    'total': 1,
                    'passed': 0,
                    'failed': 1,
                    'pass_rate': 0
                },
                'results': [{
                    'case_id': test_case.id,
                    'case_name': test_case.name,
                    'type': 'api',
                    'passed': False,
                    'response_time_ms': response_time_ms,
                    'message': f'执行异常: {str(e)}',
                    'request': {
                        'method': method,
                        'url': url,
                        'headers': headers,
                        'body': body
                    },
                    'response': {
                        'status_code': 0,
                        'headers': {},
                        'body': ''
                    },
                    'assertions': assertion_results
                }]
            }

            test_result = TestResult.objects.create(
                test_type='api',
                name=test_case.name,
                source='single',
                project=test_case.project,
                api_test_case=test_case,
                status='error',
                executed_by=request.user,
                duration_ms=response_time_ms,
                error_message=str(e),
                test_log=json.dumps(error_log, ensure_ascii=False, default=str),
            )
            # 回填 legacy_test_result_id
            case_result.legacy_test_result_id = test_result.id
            case_result.save(update_fields=['legacy_test_result_id'])
            return Response({
                'status_code': 0,
                'response_body': '',
                'response_headers': {},
                'response_time_ms': response_time_ms,
                'passed': False,
                'expected_status': test_case.expected_status,
                'assertion_results': assertion_results,
                'error_message': str(e),
                'result_id': result.id,
                'run_id': test_run.id,
                'case_result_id': case_result.id,
                'curl': curl_str,
            })
    
    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        """
        获取测试用例的执行历史
        GET /api/qa/api-cases/{id}/results/
        """
        test_case = self.get_object()
        results = test_case.results.all()[:20]  # 最近20条
        serializer = ApiTestResultSerializer(results, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='linked-tasks')
    def linked_tasks(self, request, pk=None):
        test_case = self.get_object()
        tasks = test_case.related_tasks.select_related('column', 'assignee').prefetch_related('tags')
        from room.serializers import TaskSerializer
        return Response(TaskSerializer(tasks, many=True).data)


class ApiTestResultViewSet(viewsets.ReadOnlyModelViewSet):
    """API 测试结果 ViewSet（只读）"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = ApiTestResultSerializer
    queryset = ApiTestResult.objects.all()
    
    def get_queryset(self):
        """根据测试用例ID筛选"""
        queryset = ApiTestResult.objects.all()
        test_case_id = self.request.query_params.get('test_case')
        if test_case_id:
            queryset = queryset.filter(test_case_id=test_case_id)
        return queryset


def execute_api_test_cases(case_ids):
    """
    批量执行 API 测试用例（使用真实 HTTP 请求）
    :param case_ids: 测试用例ID列表
    :return: 执行结果列表
    """
    from .test_executor import execute_api_test_cases as executor
    return executor(case_ids)
