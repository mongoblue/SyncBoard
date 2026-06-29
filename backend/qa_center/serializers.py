from django.utils import timezone
from rest_framework import serializers
from .models import (
    ApiTestCase, ApiTestResult, UiTestCase, TestResult, TestScreenshot, TestTask,
    PerformanceTestCase, PerformanceTestResult,
    ApiAutoTestSuite, ApiAutoTestCase, ApiAutoTestAssertion,
    ApiAutoTestResult, ApiAutoTestCaseResult,
    TestRunPlan,
    TestEnvironment, TestGlobalVar,
    ApiAutoTestExtractor,
)


TEST_TASK_CASE_PROJECT_ERROR = '测试用例不存在或不属于本项目'


def validate_test_task_config_cases(test_config, project):
    if test_config is None:
        return test_config
    if not isinstance(test_config, dict):
        raise serializers.ValidationError('测试配置格式无效')
    if project is None:
        return test_config

    case_specs = (
        ('api_cases', ApiTestCase),
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


class ApiTestCaseSerializer(serializers.ModelSerializer):
    """API 测试用例序列化器"""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    last_result = serializers.SerializerMethodField()
    assertions = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
        write_only=True
    )

    class Meta:
        model = ApiTestCase
        fields = [
            'id', 'project', 'name', 'url', 'method',
            'headers', 'body', 'expected_status', 'assertions',
            'created_by', 'created_by_name', 'last_result',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """读取时：从 expected_response 提取 assertions"""
        data = super().to_representation(instance)
        expected_response = instance.expected_response or {}
        if isinstance(expected_response, dict):
            assertions = expected_response.get('assertions', [])
            if isinstance(assertions, list):
                data['assertions'] = assertions
            else:
                data['assertions'] = []
        else:
            data['assertions'] = []
        return data

    def create(self, validated_data):
        """创建时：将 assertions 写入 expected_response"""
        assertions = validated_data.pop('assertions', [])
        validated_data['expected_response'] = {'assertions': assertions}
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """更新时：将 assertions 写入 expected_response"""
        assertions = validated_data.pop('assertions', None)
        if assertions is not None:
            validated_data['expected_response'] = {'assertions': assertions}
        return super().update(instance, validated_data)

    def get_last_result(self, obj):
        """获取最近一次执行结果"""
        last_result = obj.results.first()
        if last_result:
            return {
                'passed': last_result.passed,
                'status_code': last_result.status_code,
                'executed_at': last_result.executed_at
            }
        return None


class ApiTestCaseListSerializer(serializers.ModelSerializer):
    """API 测试用例列表序列化器（简化版）"""
    
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = ApiTestCase
        fields = ['id', 'name', 'method', 'url', 'expected_status', 'created_by_name', 'created_at']


class ApiTestResultSerializer(serializers.ModelSerializer):
    """API 测试结果序列化器"""
    
    executed_by_name = serializers.CharField(source='executed_by.username', read_only=True)
    
    class Meta:
        model = ApiTestResult
        fields = [
            'id', 'test_case', 'status_code', 'response_body',
            'response_headers', 'response_time_ms', 'passed',
            'assertion_results', 'error_message', 'executed_by', 'executed_by_name', 'executed_at'
        ]
        read_only_fields = ['executed_at']


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

    class Meta:
        model = TestResult
        fields = [
            'id', 'test_type', 'test_type_display', 'name', 'status', 'status_display',
            'project', 'project_name', 'executed_by', 'executed_by_name',
            'started_at', 'completed_at', 'duration_ms', 'created_at',
            'screenshot_count'
        ]

    def get_screenshot_count(self, obj):
        return obj.screenshots.count()


class TestResultDetailSerializer(serializers.ModelSerializer):
    """测试结果详情序列化器"""

    test_type_display = serializers.CharField(source='get_test_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    executed_by_name = serializers.CharField(source='executed_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    screenshots = TestScreenshotSerializer(many=True, read_only=True)
    api_test_case_name = serializers.CharField(source='api_test_case.name', read_only=True)
    ui_test_case_name = serializers.CharField(source='ui_test_case.name', read_only=True)

    class Meta:
        model = TestResult
        fields = [
            'id', 'test_type', 'test_type_display', 'name', 'status', 'status_display',
            'project', 'project_name', 'api_test_case', 'api_test_case_name',
            'ui_test_case', 'ui_test_case_name', 'executed_by', 'executed_by_name',
            'started_at', 'completed_at', 'duration_ms', 'test_params', 'test_steps',
            'expected_result', 'actual_result', 'error_message', 'test_log',
            'response_time_ms', 'throughput', 'error_rate', 'concurrent_users',
            'test_environment', 'browser_info', 'user_agent',
            'task_id', 'error_code', 'error_traceback', 'worker_pid', 'temp_dir_path', 'aborted',
            'screenshots', 'created_at', 'updated_at'
        ]


class TestResultCreateSerializer(serializers.ModelSerializer):
    """测试结果创建序列化器"""

    class Meta:
        model = TestResult
        fields = [
            'test_type', 'name', 'project', 'api_test_case', 'ui_test_case',
            'status', 'test_params', 'test_steps', 'expected_result',
            'test_environment', 'browser_info'
        ]

    def create(self, validated_data):
        validated_data['executed_by'] = self.context['request'].user
        validated_data['started_at'] = timezone.now()
        return super().create(validated_data)


# ==================== 测试任务序列化器 ====================

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

    class Meta:
        model = TestTask
        fields = [
            'id', 'name', 'description', 'test_type', 'test_type_display',
            'trigger_type', 'trigger_type_display', 'status', 'status_display',
            'project', 'project_name', 'test_config', 'cron_expression', 'webhook_url',
            'execution_count', 'last_executed', 'last_result_detail',
            'notify_on_success', 'notify_on_failure', 'notification_channels',
            'is_active', 'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'execution_count', 'last_executed', 'created_at', 'updated_at']


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
    # 显式定义 body 为 CharField，保持字符串类型，允许null
    body = serializers.CharField(allow_blank=True, allow_null=True, required=False, default='')
    # 显式定义 headers，确保返回对象而不是null
    headers = serializers.JSONField(default=dict)
    # 添加 project_id 字段，方便前端使用
    project_id = serializers.PrimaryKeyRelatedField(source='project', read_only=True)

    class Meta:
        model = PerformanceTestCase
        fields = [
            'id', 'project', 'project_id', 'name', 'description', 'url', 'method',
            'headers', 'body', 'concurrent_users', 'duration_seconds',
            'ramp_up_seconds', 'requests_per_second', 'expected_response_time_ms',
            'expected_throughput', 'expected_error_rate',
            'created_by', 'created_by_name', 'last_result',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_last_result(self, obj):
        """获取最近一次执行结果"""
        last_result = obj.results.first()
        if last_result:
            return {
                'id': last_result.id,
                'avg_response_time_ms': last_result.avg_response_time_ms,
                'throughput': last_result.throughput,
                'error_rate': last_result.error_rate,
                'executed_at': last_result.executed_at
            }
        return None


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
            'concurrent_users', 'duration_seconds', 'created_by_name', 'created_at', 'is_active'
        ]


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
            'id', 'suite', 'name', 'description', 'url', 'method', 'method_display',
            'headers', 'content_type', 'body',
            'query_params', 'form_files', 'enable_cookie_session',
            'expected_status',
            'is_active', 'sort_order', 'assertions', 'extractors',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


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
        last_result = obj.test_results.first()
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
        last_result = obj.test_results.first()
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


class ApiAutoTestCaseResultSerializer(serializers.ModelSerializer):
    """API自动化用例执行结果序列化器"""
    case_name = serializers.CharField(source='case.name', read_only=True)
    case_url = serializers.CharField(source='case.url', read_only=True)
    case_method = serializers.CharField(source='case.method', read_only=True)

    class Meta:
        model = ApiAutoTestCaseResult
        fields = [
            'id', 'test_result', 'case', 'case_name', 'case_url', 'case_method',
            'status_code', 'response_body', 'response_headers', 'response_time_ms',
            'passed', 'assertion_details', 'error_message', 'executed_at'
        ]


class ApiAutoTestCaseResultBriefSerializer(serializers.ModelSerializer):
    """轻量列表用 - 不返回 response_body / response_headers，避免单条结果膨胀。"""

    case_name = serializers.CharField(source='case.name', read_only=True)
    case_url = serializers.CharField(source='case.url', read_only=True)
    case_method = serializers.CharField(source='case.method', read_only=True)
    assertion_total = serializers.SerializerMethodField()
    assertion_passed = serializers.SerializerMethodField()
    error_summary = serializers.SerializerMethodField()

    class Meta:
        model = ApiAutoTestCaseResult
        fields = [
            'id', 'case', 'case_name', 'case_url', 'case_method',
            'status_code', 'response_time_ms', 'passed',
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
        # 取第一个失败断言的 error_message
        for a in (obj.assertion_details or []):
            if not a.get('passed') and a.get('error_message'):
                return str(a['error_message'])[:300]
        return ''


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

