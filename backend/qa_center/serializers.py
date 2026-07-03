from django.utils import timezone
from rest_framework import serializers
from .models import (
    UiTestCase, TestResult, TestScreenshot, TestTask,
    PerformanceTestCase, PerformanceTestResult,
    ApiAutoTestSuite, ApiAutoTestCase, ApiAutoTestAssertion,
    ApiAutoTestResult, ApiAutoTestCaseResult,
    TestRunPlan,
    TestEnvironment, TestGlobalVar,
    ApiAutoTestExtractor,
    CiCdConfig,
)


def _latest_performance_case_result(obj):
    return obj.results.select_related('test_result').order_by(
        '-test_result__started_at',
        '-executed_at',
        '-id',
    ).first()


def _latest_auto_suite_result(obj):
    return obj.test_results.order_by(
        '-started_at',
        '-created_at',
        '-id',
    ).first()


TEST_TASK_CASE_PROJECT_ERROR = '测试用例不存在或不属于本项目'


def validate_test_task_config_cases(test_config, project):
    if test_config is None:
        return test_config
    if not isinstance(test_config, dict):
        raise serializers.ValidationError('测试配置格式无效')
    if project is None:
        return test_config

    case_specs = (
        ('api_cases', ApiAutoTestCase),
        ('ui_cases', UiTestCase),
    )
    for field_name, model_class in case_specs:
        case_ids = test_config.get(field_name)
        if case_ids is None:
            continue
        if not isinstance(case_ids, list):
            raise serializers.ValidationError({field_name: '测试用例列表格式无效'})
        if not case_ids:
            continue

        matching_count = model_class.objects.filter(
            id__in=case_ids,
            project=project,
        ).values('id').distinct().count()
        if matching_count != len(set(case_ids)):
            raise serializers.ValidationError({field_name: TEST_TASK_CASE_PROJECT_ERROR})

    return test_config


class ApiTestRunRequestSerializer(serializers.Serializer):
    """API 测试运行请求序列化器"""

    url = serializers.CharField(required=False)
    method = serializers.ChoiceField(choices=[('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'), ('PATCH', 'PATCH'), ('DELETE', 'DELETE'), ('HEAD', 'HEAD'), ('OPTIONS', 'OPTIONS')], required=False)
    headers = serializers.JSONField(required=False, default=dict)
    body = serializers.JSONField(required=False, default=dict)


class ApiTestRunResponseSerializer(serializers.Serializer):
    """API 测试运行响应序列化器"""

    status_code = serializers.IntegerField()
    response_body = serializers.CharField(allow_blank=True)
    response_headers = serializers.JSONField()
    response_time_ms = serializers.IntegerField()
    passed = serializers.BooleanField()
    expected_status = serializers.IntegerField(allow_null=True)
    error_message = serializers.CharField(allow_blank=True, required=False)


# ==================== UI 测试序列化器 ====================

class UiTestCaseSerializer(serializers.ModelSerializer):
    """UI 测试用例序列化器"""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = UiTestCase
        fields = [
            'id', 'project', 'name', 'url', 'steps',
            'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class UiTestCaseListSerializer(serializers.ModelSerializer):
    """UI 测试用例列表序列化器（简化版）"""
    
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    step_count = serializers.SerializerMethodField()
    
    class Meta:
        model = UiTestCase
        fields = ['id', 'name', 'url', 'steps', 'step_count', 'created_by_name', 'created_at']
    
    def get_step_count(self, obj):
        """获取步骤数"""
        if isinstance(obj.steps, list):
            return len(obj.steps)
        return 0


class UiTestCaseRunSerializer(serializers.Serializer):
    """UI 测试运行响应序列化器"""

    success = serializers.BooleanField()
    screenshot = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    logs = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    error = serializers.CharField(allow_blank=True, allow_null=True, required=False)


# ==================== 测试结果序列化器 ====================

class TestScreenshotSerializer(serializers.ModelSerializer):
    """测试截图序列化器"""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = TestScreenshot
        fields = ['id', 'name', 'description', 'image', 'image_url', 'step_index', 'created_at']

    def get_image_url(self, obj):
        """获取截图完整URL"""
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class TestResultListSerializer(serializers.ModelSerializer):
    """测试结果列表序列化器"""

    test_type_display = serializers.CharField(source='get_test_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    executed_by_name = serializers.CharField(source='executed_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    screenshot_count = serializers.SerializerMethodField()
    api_auto_result_id = serializers.IntegerField(read_only=True, default=None)
    test_run_id = serializers.SerializerMethodField()
    expectation_type = serializers.SerializerMethodField()
    default_assertion_policy = serializers.SerializerMethodField()
    expected_status = serializers.SerializerMethodField()
    semantic_status = serializers.SerializerMethodField()
    semantic_label = serializers.SerializerMethodField()

    class Meta:
        model = TestResult
        fields = [
            'id', 'test_type', 'test_type_display', 'name', 'status', 'status_display',
            'project', 'project_name', 'executed_by', 'executed_by_name',
            'started_at', 'completed_at', 'duration_ms', 'created_at',
            'screenshot_count', 'api_auto_result_id', 'test_run_id',
            'expectation_type', 'default_assertion_policy', 'expected_status',
            'semantic_status', 'semantic_label',
        ]

    def get_screenshot_count(self, obj):
        return obj.screenshots.count()

    def get_test_run_id(self, obj):
        tp = obj.test_params or {}
        return tp.get('test_run_id')

    def _semantics(self, obj):
        return _mirrored_test_result_semantics(obj)

    def get_expectation_type(self, obj):
        return self._semantics(obj)['expectation_type']

    def get_default_assertion_policy(self, obj):
        return self._semantics(obj)['default_assertion_policy']

    def get_expected_status(self, obj):
        return self._semantics(obj)['expected_status']

    def get_semantic_status(self, obj):
        return self._semantics(obj)['semantic_status']

    def get_semantic_label(self, obj):
        return self._semantics(obj)['semantic_label']


class TestResultDetailSerializer(serializers.ModelSerializer):
    """测试结果详情序列化器"""

    test_type_display = serializers.CharField(source='get_test_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    executed_by_name = serializers.CharField(source='executed_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    screenshots = TestScreenshotSerializer(many=True, read_only=True)
    ui_test_case_name = serializers.CharField(source='ui_test_case.name', read_only=True)
    expectation_type = serializers.SerializerMethodField()
    default_assertion_policy = serializers.SerializerMethodField()
    expected_status = serializers.SerializerMethodField()
    semantic_status = serializers.SerializerMethodField()
    semantic_label = serializers.SerializerMethodField()

    class Meta:
        model = TestResult
        fields = [
            'id', 'test_type', 'test_type_display', 'name', 'status', 'status_display',
            'project', 'project_name',
            'ui_test_case', 'ui_test_case_name', 'executed_by', 'executed_by_name',
            'started_at', 'completed_at', 'duration_ms', 'test_params', 'test_steps',
            'expected_result', 'actual_result', 'error_message', 'test_log',
            'response_time_ms', 'throughput', 'error_rate', 'concurrent_users',
            'test_environment', 'browser_info', 'user_agent',
            'task_id', 'error_code', 'error_traceback', 'worker_pid', 'temp_dir_path', 'aborted',
            'screenshots', 'created_at', 'updated_at',
            'expectation_type', 'default_assertion_policy', 'expected_status',
            'semantic_status', 'semantic_label',
        ]

    def _semantics(self, obj):
        return _mirrored_test_result_semantics(obj)

    def get_expectation_type(self, obj):
        return self._semantics(obj)['expectation_type']

    def get_default_assertion_policy(self, obj):
        return self._semantics(obj)['default_assertion_policy']

    def get_expected_status(self, obj):
        return self._semantics(obj)['expected_status']

    def get_semantic_status(self, obj):
        return self._semantics(obj)['semantic_status']

    def get_semantic_label(self, obj):
        return self._semantics(obj)['semantic_label']


class TestResultCreateSerializer(serializers.ModelSerializer):
    """测试结果创建序列化器"""

    class Meta:
        model = TestResult
        fields = [
            'test_type', 'name', 'project', 'ui_test_case',
            'status', 'test_params', 'test_steps', 'expected_result',
            'test_environment', 'browser_info'
        ]

    def create(self, validated_data):
        validated_data['executed_by'] = self.context['request'].user
        validated_data['started_at'] = timezone.now()
        return super().create(validated_data)


def _mirrored_test_result_semantics(test_result):
    auto_result = getattr(test_result, 'api_auto_result', None)
    if not auto_result:
        if test_result.status == 'passed':
            return {
                'semantic_status': 'result_passed',
                'semantic_label': '通过',
                'expectation_type': None,
                'default_assertion_policy': None,
                'expected_status': None,
            }
        if test_result.status == 'failed':
            return {
                'semantic_status': 'result_failed',
                'semantic_label': '失败',
                'expectation_type': None,
                'default_assertion_policy': None,
                'expected_status': None,
            }
        if test_result.status == 'error':
            return {
                'semantic_status': 'result_error',
                'semantic_label': '错误',
                'expectation_type': None,
                'default_assertion_policy': None,
                'expected_status': None,
            }
        return {
            'semantic_status': f'result_{test_result.status}',
            'semantic_label': test_result.get_status_display(),
            'expectation_type': None,
            'default_assertion_policy': None,
            'expected_status': None,
        }

    case_results = auto_result.case_results.order_by('executed_at', 'id')
    if case_results.count() != 1:
        if test_result.status == 'passed':
            return {
                'semantic_status': 'result_passed',
                'semantic_label': '通过',
                'expectation_type': None,
                'default_assertion_policy': None,
                'expected_status': None,
            }
        if test_result.status == 'failed':
            return {
                'semantic_status': 'result_failed',
                'semantic_label': '失败',
                'expectation_type': None,
                'default_assertion_policy': None,
                'expected_status': None,
            }
        if test_result.status == 'error':
            return {
                'semantic_status': 'result_error',
                'semantic_label': '错误',
                'expectation_type': None,
                'default_assertion_policy': None,
                'expected_status': None,
            }
        return {
            'semantic_status': f'result_{test_result.status}',
            'semantic_label': test_result.get_status_display(),
            'expectation_type': None,
            'default_assertion_policy': None,
            'expected_status': None,
        }

    first_case = case_results.first()
    return _result_semantics(
        first_case.result_metadata,
        passed=first_case.passed,
        failure_type=first_case.failure_type,
        status_code=first_case.status_code,
    )

class TestTaskListSerializer(serializers.ModelSerializer):
    """测试任务列表序列化器"""

    test_type_display = serializers.CharField(source='get_test_type_display', read_only=True)
    trigger_type_display = serializers.CharField(source='get_trigger_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    last_result_summary = serializers.SerializerMethodField()

    class Meta:
        model = TestTask
        fields = [
            'id', 'name', 'description', 'test_type', 'test_type_display',
            'trigger_type', 'trigger_type_display', 'status', 'status_display',
            'project', 'project_name', 'execution_count', 'last_executed',
            'last_result_summary', 'is_active', 'created_by_name', 'created_at'
        ]

    def get_last_result_summary(self, obj):
        """获取最后一次执行结果摘要"""
        if obj.last_result:
            return {
                'id': obj.last_result.id,
                'status': obj.last_result.status,
                'passed': obj.last_result.status == 'passed',
                'duration_ms': obj.last_result.duration_ms,
                'created_at': obj.last_result.created_at
            }
        return None


class TestTaskDetailSerializer(serializers.ModelSerializer):
    """测试任务详情序列化器"""

    test_type_display = serializers.CharField(source='get_test_type_display', read_only=True)
    trigger_type_display = serializers.CharField(source='get_trigger_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    last_result_detail = TestResultListSerializer(source='last_result', read_only=True)
    schedule_backend = serializers.SerializerMethodField()

    class Meta:
        model = TestTask
        fields = [
            'id', 'name', 'description', 'test_type', 'test_type_display',
            'trigger_type', 'trigger_type_display', 'status', 'status_display',
            'project', 'project_name', 'test_config', 'cron_expression', 'webhook_url',
            'execution_count', 'last_executed', 'last_result_detail',
            'notify_on_success', 'notify_on_failure', 'notification_channels',
            'is_active', 'created_by', 'created_by_name', 'created_at', 'updated_at',
            'schedule_backend',
        ]
        read_only_fields = ['created_by', 'execution_count', 'last_executed',
                           'created_at', 'updated_at', 'schedule_backend']

    def get_schedule_backend(self, obj):
        if obj.trigger_type == 'scheduled':
            try:
                import django_celery_beat  # noqa: F401
                return 'django_celery_beat'
            except ImportError:
                return 'unavailable'
        return None


class TestTaskCreateSerializer(serializers.ModelSerializer):
    """测试任务创建序列化器"""

    class Meta:
        model = TestTask
        fields = [
            'name', 'description', 'test_type', 'project',
            'trigger_type', 'cron_expression', 'webhook_url',
            'test_config', 'notify_on_success', 'notify_on_failure', 'notification_channels'
        ]

    def validate(self, attrs):
        validate_test_task_config_cases(attrs.get('test_config'), attrs.get('project'))
        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        validated_data['status'] = 'idle'
        return super().create(validated_data)


class TestTaskUpdateSerializer(serializers.ModelSerializer):
    """测试任务更新序列化器"""

    class Meta:
        model = TestTask
        fields = [
            'name', 'description', 'test_type',
            'trigger_type', 'cron_expression', 'webhook_url',
            'test_config', 'notify_on_success', 'notify_on_failure', 'notification_channels',
            'is_active'
        ]

    def validate(self, attrs):
        project = self.instance.project if self.instance else None
        validate_test_task_config_cases(attrs.get('test_config'), project)
        return attrs


class TestTaskExecuteSerializer(serializers.Serializer):
    """测试任务执行请求序列化器"""

    message = serializers.CharField(read_only=True)
    execution_id = serializers.IntegerField(read_only=True)
    task = TestTaskListSerializer(read_only=True)


# ==================== 性能测试序列化器 ====================

class PerformanceTestCaseSerializer(serializers.ModelSerializer):
    """性能测试用例序列化器"""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    last_result = serializers.SerializerMethodField()
    body = serializers.CharField(allow_blank=True, allow_null=True, required=False, default='')
    headers = serializers.JSONField(default=dict)
    query_params = serializers.JSONField(default=dict, required=False)
    auth_config = serializers.JSONField(default=dict, required=False)
    steps = serializers.JSONField(default=list, required=False)
    assertions = serializers.JSONField(default=list, required=False)
    project_id = serializers.PrimaryKeyRelatedField(source='project', read_only=True)

    class Meta:
        model = PerformanceTestCase
        fields = [
            'id', 'project', 'project_id', 'name', 'description', 'url', 'method',
            'headers', 'body', 'query_params', 'body_type',
            'request_timeout', 'follow_redirects', 'verify_ssl',
            'auth_config', 'steps', 'assertions',
            'concurrent_users', 'duration_seconds', 'ramp_up_seconds',
            'requests_per_second', 'think_time_min', 'think_time_max', 'weight',
            'expected_response_time_ms', 'expected_throughput', 'expected_error_rate',
            'created_by', 'created_by_name', 'last_result',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_last_result(self, obj):
        last_result = _latest_performance_case_result(obj)
        if last_result:
            return {
                'id': last_result.id,
                'avg_response_time_ms': last_result.avg_response_time_ms,
                'throughput': last_result.throughput,
                'error_rate': last_result.error_rate,
                'executed_at': last_result.executed_at
            }
        return None

    def to_representation(self, instance):
        """序列化时屏蔽 auth_config 中的敏感 token。"""
        data = super().to_representation(instance)
        auth = data.get('auth_config', {}) or {}
        if auth.get('token') and not str(auth.get('token', '')).startswith('{{'):
            token = str(auth.get('token', ''))
            auth = dict(auth)
            auth['token'] = token[:4] + '****' + token[-4:] if len(token) > 8 else '****'
            data['auth_config'] = auth
        return data


class PerformanceTestCaseListSerializer(serializers.ModelSerializer):
    """性能测试用例列表序列化器（简化版）"""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(source='project', read_only=True)
    headers = serializers.JSONField(default=dict)
    body = serializers.CharField(allow_blank=True, allow_null=True, default='')

    class Meta:
        model = PerformanceTestCase
        fields = [
            'id', 'project_id', 'name', 'url', 'method', 'headers', 'body',
            'concurrent_users', 'duration_seconds', 'ramp_up_seconds',
            'created_by_name', 'created_at', 'is_active'
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # 列表页不返回敏感认证信息
        data.pop('auth_config', None)
        return data


class PerformanceTestResultSerializer(serializers.ModelSerializer):
    """性能测试结果序列化器"""

    executed_by_name = serializers.CharField(source='executed_by.username', read_only=True)
    test_case_name = serializers.CharField(source='test_case.name', read_only=True)

    class Meta:
        model = PerformanceTestResult
        fields = [
            'id', 'test_case', 'test_case_name', 'test_result',
            'total_requests', 'successful_requests', 'failed_requests',
            'avg_response_time_ms', 'min_response_time_ms', 'max_response_time_ms',
            'p50_response_time_ms', 'p90_response_time_ms', 'p95_response_time_ms', 'p99_response_time_ms',
            'throughput', 'error_rate',
            'response_time_distribution', 'throughput_over_time',
            'response_time_over_time', 'error_details',
            'step_results', 'assertion_results',
            'executed_by', 'executed_by_name', 'executed_at'
        ]
        read_only_fields = ['executed_at']


class PerformanceTestResultListSerializer(serializers.ModelSerializer):
    """性能测试结果列表序列化器（简化版）"""

    executed_by_name = serializers.CharField(source='executed_by.username', read_only=True)
    test_case_name = serializers.CharField(source='test_case.name', read_only=True)

    class Meta:
        model = PerformanceTestResult
        fields = [
            'id', 'test_case', 'test_case_name',
            'avg_response_time_ms', 'throughput', 'error_rate',
            'executed_by_name', 'executed_at'
        ]


class PerformanceTestExecuteSerializer(serializers.Serializer):
    """性能测试执行请求序列化器"""

    message = serializers.CharField(read_only=True)
    execution_id = serializers.IntegerField(read_only=True)
    test_case = PerformanceTestCaseListSerializer(read_only=True)


class ApiAutoTestAssertionSerializer(serializers.ModelSerializer):
    """API自动化测试断言序列化器"""
    assertion_type_display = serializers.CharField(
        source='get_assertion_type_display', read_only=True
    )

    class Meta:
        model = ApiAutoTestAssertion
        fields = [
            'id', 'case', 'assertion_type', 'assertion_type_display',
            'json_path', 'expected_value', 'comparison_operator',
            'is_active', 'error_message', 'sort_order'
        ]


class ApiAutoTestExtractorSerializer(serializers.ModelSerializer):
    """变量抽取器序列化器 —— M3.3"""
    source_display = serializers.CharField(source='get_source_display', read_only=True)

    class Meta:
        model = ApiAutoTestExtractor
        fields = [
            'id', 'case', 'name', 'source', 'source_display',
            'expression', 'default_value', 'is_active', 'sort_order',
        ]

    def validate_name(self, value):
        v = (value or '').strip()
        if not v:
            raise serializers.ValidationError('变量名不能为空')
        import re as _re
        if not _re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', v):
            raise serializers.ValidationError('变量名只能包含字母数字下划线，且不以数字开头')
        return v

    def validate(self, attrs):
        source = attrs.get('source') or getattr(self.instance, 'source', 'body')
        expression = attrs.get('expression', '') if 'expression' in attrs else getattr(self.instance, 'expression', '')
        if source in ('body', 'header', 'cookie') and not (expression or '').strip():
            raise serializers.ValidationError({'expression': f'source={source} 时表达式必填'})
        return attrs


class ApiAutoTestCaseSerializer(serializers.ModelSerializer):
    """API自动化测试用例序列化器"""
    assertions = ApiAutoTestAssertionSerializer(many=True, read_only=True)
    extractors = ApiAutoTestExtractorSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.username', read_only=True
    )
    method_display = serializers.CharField(source='get_method_display', read_only=True)

    def validate_query_params(self, value):
        """允许 dict 或 list-of-pairs；其它形态拒绝以免运行时偷偷吃掉。"""
        if value in (None, '', [], {}):
            return value if value is not None else {}
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    continue
                if isinstance(item, dict) and 'name' in item:
                    continue
                raise serializers.ValidationError('list 形态每项必须为 [key, value] 或 {name, value}')
            return value
        raise serializers.ValidationError('必须为 dict 或 list')

    def validate_form_files(self, value):
        if value in (None, '', []):
            return value or []
        if not isinstance(value, list):
            raise serializers.ValidationError('必须为 list')
        for spec in value:
            if not isinstance(spec, dict):
                raise serializers.ValidationError('每项必须为对象')
            if not (spec.get('name') or spec.get('field')):
                raise serializers.ValidationError('每项必须含 name 字段')
        return value

    class Meta:
        model = ApiAutoTestCase
        fields = [
            'id', 'suite', 'project', 'environment', 'name', 'description', 'url', 'method', 'method_display',
            'headers', 'content_type', 'body',
            'query_params', 'form_files', 'enable_cookie_session',
            'expected_status',
            'is_active', 'sort_order', 'assertions', 'extractors',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def validate(self, attrs):
        suite = attrs.get('suite') or (self.instance.suite if self.instance else None)
        project = attrs.get('project') or (self.instance.project if self.instance else None)
        if not suite and not project:
            raise serializers.ValidationError('suite 和 project 至少需要提供一个')
        return attrs


class ApiAutoTestCaseListSerializer(serializers.ModelSerializer):
    """API自动化测试用例列表序列化器（简化版）"""
    created_by_name = serializers.CharField(
        source='created_by.username', read_only=True
    )
    assertion_count = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestCase
        fields = [
            'id', 'name', 'description', 'url', 'method', 'expected_status',
            'is_active', 'assertion_count', 'created_by_name', 'created_at'
        ]

    def get_assertion_count(self, obj):
        return obj.assertions.filter(is_active=True).count()


class ApiAutoTestSuiteSerializer(serializers.ModelSerializer):
    """API自动化测试套件序列化器"""
    test_cases = ApiAutoTestCaseListSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.username', read_only=True
    )
    case_count = serializers.SerializerMethodField()
    last_result = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestSuite
        fields = [
            'id', 'project', 'name', 'description', 'is_active',
            'test_cases', 'case_count', 'last_result',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_case_count(self, obj):
        return obj.test_cases.filter(is_active=True).count()

    def get_last_result(self, obj):
        last_result = _latest_auto_suite_result(obj)
        if last_result:
            return {
                'id': last_result.id,
                'status': last_result.status,
                'passed_cases': last_result.passed_cases,
                'failed_cases': last_result.failed_cases,
                'created_at': last_result.created_at
            }
        return None


class ApiAutoTestSuiteListSerializer(serializers.ModelSerializer):
    """API自动化测试套件列表序列化器（简化版）"""
    created_by_name = serializers.CharField(
        source='created_by.username', read_only=True
    )
    case_count = serializers.SerializerMethodField()
    last_run = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestSuite
        fields = [
            'id', 'name', 'description', 'is_active',
            'case_count', 'last_run', 'created_by_name', 'created_at'
        ]

    def get_case_count(self, obj):
        return obj.test_cases.filter(is_active=True).count()

    def get_last_run(self, obj):
        last_result = _latest_auto_suite_result(obj)
        if last_result:
            return {
                'id': last_result.id,
                'status': last_result.status,
                'passed_cases': last_result.passed_cases,
                'failed_cases': last_result.failed_cases,
                'duration_ms': last_result.duration_ms,
                'created_at': last_result.created_at
            }
        return None


def _result_semantics(metadata, *, passed, failure_type, status_code=None):
    payload = metadata if isinstance(metadata, dict) else {}
    expectation_type = payload.get('expectation_type') or 'success_response'
    default_assertion_policy = payload.get('default_assertion_policy') or (
        'expected_error_response' if expectation_type == 'error_response' else 'success_response'
    )
    expected_status = payload.get('expected_status')
    provider = payload.get('provider') or 'http'

    semantic_status = payload.get('semantic_status')
    semantic_label = payload.get('semantic_label')
    if not semantic_status or not semantic_label:
        if expectation_type == 'error_response':
            if passed:
                semantic_status = 'expected_error_matched'
                semantic_label = '预期错误响应且匹配成功'
            elif failure_type == 'assertion_failed':
                semantic_status = 'expected_error_unmatched'
                semantic_label = '预期错误响应但未匹配'
            else:
                semantic_status = 'expected_error_execution_error'
                semantic_label = '预期错误场景执行异常'
        else:
            if passed:
                semantic_status = 'success_response_passed'
                semantic_label = '成功响应断言通过'
            else:
                semantic_status = 'success_response_failed'
                semantic_label = '测试失败'

    return {
        'provider': provider,
        'expectation_type': expectation_type,
        'default_assertion_policy': default_assertion_policy,
        'expected_status': expected_status,
        'semantic_status': semantic_status,
        'semantic_label': semantic_label,
        'actual_status_code': status_code,
    }


class ApiAutoTestCaseResultSerializer(serializers.ModelSerializer):
    """API自动化用例执行结果序列化器"""
    case_name = serializers.CharField(source='case.name', read_only=True)
    case_url = serializers.CharField(source='case.url', read_only=True)
    case_method = serializers.CharField(source='case.method', read_only=True)
    summary = serializers.SerializerMethodField()
    diagnosis = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    expectation_type = serializers.SerializerMethodField()
    default_assertion_policy = serializers.SerializerMethodField()
    expected_status = serializers.SerializerMethodField()
    semantic_status = serializers.SerializerMethodField()
    semantic_label = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestCaseResult
        fields = [
            'id', 'test_result', 'case', 'case_name', 'case_url', 'case_method',
            'status_code', 'response_body', 'response_headers', 'response_time_ms',
            'passed', 'failure_type', 'assertion_details', 'error_message',
            'trace_id', 'raw_status', 'error_code',
            'request_snapshot', 'response_snapshot', 'curl',
            'extracted_variables_preview', 'result_metadata',
            'provider', 'expectation_type', 'default_assertion_policy', 'expected_status',
            'semantic_status', 'semantic_label',
            'summary', 'diagnosis',
            'executed_at'
        ]

    def get_summary(self, obj):
        metadata = obj.result_metadata or {}
        if isinstance(metadata, dict):
            return metadata.get('summary') or ''
        return ''

    def get_diagnosis(self, obj):
        metadata = obj.result_metadata or {}
        if isinstance(metadata, dict):
            return metadata.get('diagnosis') or None
        return None

    def _semantics(self, obj):
        return _result_semantics(
            obj.result_metadata,
            passed=obj.passed,
            failure_type=obj.failure_type,
            status_code=obj.status_code,
        )

    def get_provider(self, obj):
        return self._semantics(obj)['provider']

    def get_expectation_type(self, obj):
        return self._semantics(obj)['expectation_type']

    def get_default_assertion_policy(self, obj):
        return self._semantics(obj)['default_assertion_policy']

    def get_expected_status(self, obj):
        return self._semantics(obj)['expected_status']

    def get_semantic_status(self, obj):
        return self._semantics(obj)['semantic_status']

    def get_semantic_label(self, obj):
        return self._semantics(obj)['semantic_label']


class ApiAutoTestCaseResultBriefSerializer(serializers.ModelSerializer):
    """轻量列表用 - 不返回 response_body / response_headers，避免单条结果膨胀。"""

    case_name = serializers.CharField(source='case.name', read_only=True)
    case_url = serializers.CharField(source='case.url', read_only=True)
    case_method = serializers.CharField(source='case.method', read_only=True)
    assertion_total = serializers.SerializerMethodField()
    assertion_passed = serializers.SerializerMethodField()
    error_summary = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    expectation_type = serializers.SerializerMethodField()
    default_assertion_policy = serializers.SerializerMethodField()
    expected_status = serializers.SerializerMethodField()
    semantic_status = serializers.SerializerMethodField()
    semantic_label = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestCaseResult
        fields = [
            'id', 'case', 'case_name', 'case_url', 'case_method',
            'status_code', 'response_time_ms', 'passed',
            'provider', 'expectation_type', 'default_assertion_policy', 'expected_status',
            'semantic_status', 'semantic_label',
            'assertion_total', 'assertion_passed',
            'error_summary', 'executed_at',
        ]

    def get_assertion_total(self, obj):
        return len(obj.assertion_details or [])

    def get_assertion_passed(self, obj):
        return sum(1 for a in (obj.assertion_details or []) if a.get('passed'))

    def get_error_summary(self, obj):
        if obj.error_message:
            return obj.error_message[:300]
        for a in (obj.assertion_details or []):
            if not a.get('passed') and a.get('error_message'):
                return str(a['error_message'])[:300]
        return ''

    def _semantics(self, obj):
        return _result_semantics(
            obj.result_metadata,
            passed=obj.passed,
            failure_type=obj.failure_type,
            status_code=obj.status_code,
        )

    def get_provider(self, obj):
        return self._semantics(obj)['provider']

    def get_expectation_type(self, obj):
        return self._semantics(obj)['expectation_type']

    def get_default_assertion_policy(self, obj):
        return self._semantics(obj)['default_assertion_policy']

    def get_expected_status(self, obj):
        return self._semantics(obj)['expected_status']

    def get_semantic_status(self, obj):
        return self._semantics(obj)['semantic_status']

    def get_semantic_label(self, obj):
        return self._semantics(obj)['semantic_label']


class ApiAutoTestResultSerializer(serializers.ModelSerializer):
    """API自动化测试结果序列化器"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    executed_by_name = serializers.CharField(
        source='executed_by.username', read_only=True
    )
    case_results = ApiAutoTestCaseResultSerializer(many=True, read_only=True)
    pass_rate = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestResult
        fields = [
            'id', 'suite', 'name', 'status', 'status_display',
            'total_cases', 'passed_cases', 'failed_cases', 'error_cases',
            'duration_ms', 'pass_rate',
            'executed_by', 'executed_by_name',
            'started_at', 'completed_at', 'error_message',
            'case_results', 'created_at'
        ]

    def get_pass_rate(self, obj):
        if obj.total_cases > 0:
            return round(obj.passed_cases / obj.total_cases * 100, 2)
        return 0


class ApiAutoTestResultListSerializer(serializers.ModelSerializer):
    """API自动化测试结果列表序列化器（简化版）"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    executed_by_name = serializers.CharField(
        source='executed_by.username', read_only=True
    )
    pass_rate = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestResult
        fields = [
            'id', 'suite', 'name', 'status', 'status_display',
            'total_cases', 'passed_cases', 'failed_cases', 'error_cases',
            'duration_ms', 'pass_rate',
            'executed_by', 'executed_by_name',
            'started_at', 'completed_at', 'created_at'
        ]

    def get_pass_rate(self, obj):
        if obj.total_cases > 0:
            return round(obj.passed_cases / obj.total_cases * 100, 2)
        return 0


class ApiAutoTestExecuteSerializer(serializers.Serializer):
    """API自动化测试执行请求序列化器"""
    suite_id = serializers.IntegerField(required=True)
    name = serializers.CharField(max_length=200, required=False)

    def validate_suite_id(self, value):
        try:
            ApiAutoTestSuite.objects.get(id=value, is_active=True)
        except ApiAutoTestSuite.DoesNotExist:
            raise serializers.ValidationError("测试套件不存在或未启用")
        return value


# ============== M2: TestRunPlan ==============

class TestRunPlanSerializer(serializers.ModelSerializer):
    """批量执行计划序列化器"""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = TestRunPlan
        fields = [
            'id', 'project', 'project_name', 'name', 'description',
            'case_ids', 'case_count',
            'parallel', 'max_workers', 'stop_on_failure', 'case_timeout_seconds',
            'environment', 'environment_name',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    environment_name = serializers.CharField(source='environment.name', read_only=True)

    def get_case_count(self, obj):
        return len(obj.case_ids or [])

    def validate_case_ids(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('case_ids 必须是数组')
        if not value:
            raise serializers.ValidationError('至少选择一条用例')
        if len(value) > 500:
            raise serializers.ValidationError('单次最多 500 条用例')
        # 全部转 int 并去重
        try:
            normalized = list(dict.fromkeys(int(x) for x in value))
        except (TypeError, ValueError):
            raise serializers.ValidationError('case_ids 含非法 ID')
        # 校验存在性 & 项目一致性放在 viewset 里做（这里拿不到 project）
        return normalized

    def validate_max_workers(self, value):
        if value < 1 or value > 32:
            raise serializers.ValidationError('max_workers 必须在 1-32 之间')
        return value

    def validate_case_timeout_seconds(self, value):
        if value < 1 or value > 300:
            raise serializers.ValidationError('case_timeout_seconds 必须在 1-300 之间')
        return value

    def validate(self, attrs):
        if self.instance and 'project' in attrs and attrs['project'].id != self.instance.project_id:
            raise serializers.ValidationError({'project': '不允许修改计划所属项目'})

        project = attrs.get('project') or getattr(self.instance, 'project', None)
        case_ids = attrs.get('case_ids', getattr(self.instance, 'case_ids', None))
        environment = attrs.get('environment', getattr(self.instance, 'environment', None))

        if project and environment and environment.project_id != project.id:
            raise serializers.ValidationError({'environment': '运行环境不属于本项目'})

        if project and case_ids:
            existing = set(
                ApiAutoTestCase.objects
                .filter(id__in=case_ids, suite__project=project)
                .values_list('id', flat=True)
            )
            missing = [cid for cid in case_ids if cid not in existing]
            if missing:
                raise serializers.ValidationError({
                    'case_ids': f'以下用例不存在或不属于本项目: {missing}'
                })
        return attrs


class TestRunPlanExecuteSerializer(serializers.Serializer):
    """触发执行时的可选 override 参数"""
    parallel = serializers.BooleanField(required=False)
    max_workers = serializers.IntegerField(required=False, min_value=1, max_value=32)
    stop_on_failure = serializers.BooleanField(required=False)
    environment_id = serializers.IntegerField(required=False, allow_null=True)


# ============== M3.2: 环境与全局变量序列化器 ==============


class TestEnvironmentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = TestEnvironment
        fields = [
            'id', 'project', 'name', 'base_url', 'variables',
            'allowed_hosts', 'allowed_cidrs',
            'description', 'is_default',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def validate_variables(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('variables 必须是 JSON 对象')
        # 键必须是字符串且不空；值不限制类型
        for k in value.keys():
            if not isinstance(k, str) or not k.strip():
                raise serializers.ValidationError('变量名必须是非空字符串')
        return value

    def validate_allowed_hosts(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('allowed_hosts 必须是数组')
        from .environment_security import normalize_allowed_host
        out = []
        try:
            for item in value:
                out.append(normalize_allowed_host(item))
        except serializers.ValidationError:
            raise
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return out

    def validate_allowed_cidrs(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('allowed_cidrs 必须是数组')
        from .environment_security import validate_allowed_cidr
        out = []
        try:
            for item in value:
                out.append(validate_allowed_cidr(item))
        except serializers.ValidationError:
            raise
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return out

    def validate(self, attrs):
        if self.instance and 'project' in attrs and attrs['project'].id != self.instance.project_id:
            raise serializers.ValidationError({'project': '不允许修改环境所属项目'})

        # 同一项目同名环境去重
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        name = attrs.get('name') or getattr(self.instance, 'name', None)
        if project and name:
            qs = TestEnvironment.objects.filter(project=project, name=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'name': '该项目下已存在同名环境'})
        return attrs


class TestGlobalVarSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    value_display = serializers.SerializerMethodField()

    class Meta:
        model = TestGlobalVar
        fields = [
            'id', 'project', 'key', 'value', 'value_display',
            'description', 'is_secret',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_value_display(self, obj):
        # 敏感变量在列表/详情里只展示掩码，写入时仍走 value 字段
        if obj.is_secret and obj.value:
            return '*' * 8
        return obj.value

    def validate_key(self, value):
        v = (value or '').strip()
        if not v:
            raise serializers.ValidationError('变量名不能为空')
        import re as _re
        if not _re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', v):
            raise serializers.ValidationError('变量名只能包含字母数字下划线，且不以数字开头')
        return v

    def validate(self, attrs):
        if self.instance and 'project' in attrs and attrs['project'].id != self.instance.project_id:
            raise serializers.ValidationError({'project': '不允许修改全局变量所属项目'})

        project = attrs.get('project') or getattr(self.instance, 'project', None)
        key = attrs.get('key') or getattr(self.instance, 'key', None)
        if project and key:
            qs = TestGlobalVar.objects.filter(project=project, key=key)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'key': '该项目下已存在同名全局变量'})
        return attrs



# ---------------------------------------------------------------------------
# CI/CD Config serializer — unified serialization with frontend compatibility aliases
# ---------------------------------------------------------------------------

class CiCdConfigSerializer(serializers.ModelSerializer):
    ci_token_display = serializers.SerializerMethodField()

    # Frontend compatibility aliases (read-only)
    type = serializers.CharField(source='ci_type', read_only=True)
    test_suite = serializers.JSONField(source='test_suite_ids', read_only=True)
    enabled = serializers.BooleanField(source='is_active', read_only=True)
    status = serializers.SerializerMethodField()
    project_id = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    # Write-only project_id that maps to the project FK
    write_only_project_id = serializers.PrimaryKeyRelatedField(
        source='project',
        queryset=CiCdConfig._meta.get_field('project').remote_field.model.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = CiCdConfig
        fields = [
            "id", "name", "ci_type", "type",
            "ci_url", "ci_token", "ci_token_display",
            "ci_project", "ci_job_name", "verify_ssl",
            "webhook_url", "api_token", "branch",
            "auto_trigger", "test_suite_ids", "test_suite",
            "headers", "is_active", "enabled", "status",
            "project", "project_id", "write_only_project_id",
            "created_by", "created_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "created_by", "created_at", "updated_at",
            "ci_token_display", "project",
        ]
        extra_kwargs = {
            "ci_token": {"write_only": True},
            "api_token": {"write_only": True},
        }

    def get_ci_token_display(self, obj):
        """Return a masked version of ci_token for display."""
        token = obj.ci_token or ""
        if len(token) <= 4:
            return "****"
        return token[:4] + "*" * (len(token) - 4)

    def get_status(self, obj):
        return 'active' if obj.is_active else 'inactive'

    def get_project_id(self, obj):
        return str(obj.project_id) if obj.project_id else None

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else ''

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)
