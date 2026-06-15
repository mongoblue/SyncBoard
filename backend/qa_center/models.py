"""
QA Center models.

Reverse-engineered from migrations 0001-0014. Do not hand-edit field
options; any schema change should be made as a new migration and
reflected back here so the two stay in sync.
"""
from django.conf import settings
from django.db import models

from room.models import Project, Task


class ApiTestCase(models.Model):
    name = models.CharField(max_length=200, verbose_name='用例名称')
    url = models.CharField(max_length=1000, verbose_name='请求URL')
    method = models.CharField(
        choices=[
            ('GET', 'GET'),
            ('POST', 'POST'),
            ('PUT', 'PUT'),
            ('PATCH', 'PATCH'),
            ('DELETE', 'DELETE'),
            ('HEAD', 'HEAD'),
            ('OPTIONS', 'OPTIONS'),
        ],
        default='GET',
        max_length=10,
        verbose_name='请求方法',
    )
    headers = models.JSONField(blank=True, default=dict, verbose_name='请求头')
    body = models.TextField(blank=True, verbose_name='请求体')
    expected_status = models.IntegerField(blank=True, null=True, verbose_name='预期状态码')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_api_cases',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='api_test_cases',
        verbose_name='所属项目',
    )
    content_type = models.CharField(
        choices=[
            ('application/json', 'JSON'),
            ('application/x-www-form-urlencoded', 'Form'),
            ('multipart/form-data', 'Multipart'),
            ('text/plain', 'Text'),
            ('text/xml', 'XML'),
        ],
        default='application/json',
        max_length=50,
        verbose_name='Content-Type',
    )
    description = models.TextField(blank=True, verbose_name='用例描述')
    expected_response = models.JSONField(blank=True, default=dict, verbose_name='预期响应')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    related_tasks = models.ManyToManyField(
        Task,
        blank=True,
        related_name='linked_api_test_cases',
        verbose_name='关联任务',
    )
    response_extractions = models.JSONField(
        default=list, blank=True,
        verbose_name='响应变量提取',
        help_text='[{"json_path": "$.token", "var_name": "auth_token", "default": null}]'
    )

    class Meta:
        verbose_name = 'API测试用例'
        verbose_name_plural = 'API测试用例'
        db_table = 'qa_api_test_cases'
        ordering = ['-created_at']


class ApiTestResult(models.Model):
    status_code = models.IntegerField(verbose_name='响应状态码')
    response_body = models.TextField(blank=True, verbose_name='响应体')
    response_headers = models.JSONField(default=dict, verbose_name='响应头')
    response_time_ms = models.IntegerField(verbose_name='响应时间(ms)')
    passed = models.BooleanField(verbose_name='是否通过')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    executed_at = models.DateTimeField(auto_now_add=True, verbose_name='执行时间')
    assertion_results = models.JSONField(blank=True, default=list, verbose_name='断言结果详情')
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        verbose_name='执行者',
    )
    test_case = models.ForeignKey(
        ApiTestCase,
        on_delete=models.CASCADE,
        related_name='results',
        verbose_name='测试用例',
    )

    class Meta:
        verbose_name = 'API测试结果'
        verbose_name_plural = 'API测试结果'
        db_table = 'qa_api_test_results'
        ordering = ['-executed_at']


class UiTestCase(models.Model):
    name = models.CharField(max_length=200, verbose_name='测试用例名称')
    url = models.CharField(max_length=1000, verbose_name='起始URL')
    steps = models.JSONField(default=list, verbose_name='测试步骤')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_ui_cases',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='ui_test_cases',
        verbose_name='所属项目',
    )
    related_tasks = models.ManyToManyField(
        Task,
        blank=True,
        related_name='linked_ui_test_cases',
        verbose_name='关联任务',
    )

    class Meta:
        verbose_name = 'UI测试用例'
        verbose_name_plural = 'UI测试用例'
        db_table = 'qa_ui_test_cases'
        ordering = ['-created_at']


class TestResult(models.Model):
    id = models.AutoField(primary_key=True, serialize=False)
    test_type = models.CharField(
        choices=[
            ('api', '接口测试'),
            ('ui', 'UI测试'),
            ('performance', '性能测试'),
            ('regression', '回归测试'),
        ],
        max_length=20,
        verbose_name='测试类型',
    )
    name = models.CharField(max_length=200, verbose_name='测试名称')
    status = models.CharField(
        choices=[
            ('passed', '通过'),
            ('failed', '失败'),
            ('error', '错误'),
            ('running', '运行中'),
            ('pending', '待执行'),
        ],
        default='pending',
        max_length=20,
        verbose_name='测试状态',
    )
    started_at = models.DateTimeField(blank=True, null=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='完成时间')
    duration_ms = models.IntegerField(blank=True, null=True, verbose_name='执行时长(ms)')
    test_params = models.JSONField(blank=True, default=dict, null=True, verbose_name='测试参数')
    test_steps = models.JSONField(blank=True, default=list, null=True, verbose_name='测试步骤')
    expected_result = models.TextField(blank=True, null=True, verbose_name='预期结果')
    actual_result = models.TextField(blank=True, null=True, verbose_name='实际结果')
    error_message = models.TextField(blank=True, null=True, verbose_name='错误信息')
    test_log = models.TextField(blank=True, null=True, verbose_name='测试日志')
    response_time_ms = models.IntegerField(blank=True, null=True, verbose_name='响应时间(ms)')
    throughput = models.FloatField(blank=True, null=True, verbose_name='吞吐量(req/s)')
    error_rate = models.FloatField(blank=True, null=True, verbose_name='错误率(%)')
    concurrent_users = models.IntegerField(blank=True, null=True, verbose_name='并发用户数')
    test_environment = models.CharField(blank=True, max_length=200, verbose_name='测试环境')
    browser_info = models.CharField(blank=True, max_length=200, verbose_name='浏览器信息')
    user_agent = models.TextField(blank=True, verbose_name='User Agent')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    task_id = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="任务ID")
    error_code = models.CharField(max_length=64, blank=True, default="", verbose_name="错误码")
    error_traceback = models.TextField(blank=True, default="", verbose_name="错误堆栈")
    worker_pid = models.IntegerField(blank=True, null=True, verbose_name="Worker PID")
    temp_dir_path = models.CharField(max_length=512, blank=True, default="", verbose_name="临时目录")
    aborted = models.BooleanField(default=False, verbose_name="是否被中止")
    source = models.CharField(
        choices=[
            ('devops', 'DevOps执行'),
            ('single', '单个用例执行'),
        ],
        default='single',
        max_length=20,
        verbose_name='结果来源',
    )
    api_test_case = models.ForeignKey(
        ApiTestCase,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='test_results',
        verbose_name='关联API用例',
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='executed_tests',
        verbose_name='执行人员',
    )
    project = models.ForeignKey(
        Project,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name='test_results',
        verbose_name='所属项目',
    )
    ui_test_case = models.ForeignKey(
        UiTestCase,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='test_results',
        verbose_name='关联UI用例',
    )

    class Meta:
        verbose_name = '测试结果'
        verbose_name_plural = '测试结果'
        db_table = 'qa_test_results'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['test_type', 'status'], name='qa_test_res_test_ty_2fa477_idx'),
            models.Index(fields=['project', 'created_at'], name='qa_test_res_project_f62f1c_idx'),
            models.Index(fields=['executed_by', 'created_at'], name='qa_test_res_execute_f5c965_idx'),
        ]


class TestScreenshot(models.Model):
    name = models.CharField(blank=True, max_length=200, verbose_name='截图名称')
    description = models.TextField(blank=True, verbose_name='截图描述')
    image = models.ImageField(upload_to='test_screenshots/%Y/%m/%d/', verbose_name='截图文件')
    step_index = models.IntegerField(blank=True, null=True, verbose_name='步骤序号')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    test_result = models.ForeignKey(
        TestResult,
        on_delete=models.CASCADE,
        related_name='screenshots',
        verbose_name='测试结果',
    )

    class Meta:
        verbose_name = '测试截图'
        verbose_name_plural = '测试截图'
        db_table = 'qa_test_screenshots'
        ordering = ['step_index', 'created_at']


class TestTask(models.Model):
    name = models.CharField(max_length=200, verbose_name='任务名称')
    description = models.TextField(blank=True, verbose_name='任务描述')
    test_type = models.CharField(
        choices=[
            ('api', '接口测试'),
            ('ui', 'UI测试'),
            ('performance', '性能测试'),
            ('regression', '回归测试'),
        ],
        max_length=20,
        verbose_name='测试类型',
    )
    trigger_type = models.CharField(
        choices=[
            ('manual', '手动触发'),
            ('scheduled', '定时触发'),
            ('webhook', 'Webhook触发'),
        ],
        default='manual',
        max_length=20,
        verbose_name='触发方式',
    )
    cron_expression = models.CharField(blank=True, max_length=100, verbose_name='Cron表达式（定时任务）')
    webhook_url = models.CharField(blank=True, max_length=500, verbose_name='Webhook URL')
    test_config = models.JSONField(blank=True, default=dict, verbose_name='测试配置')
    status = models.CharField(
        choices=[
            ('idle', '空闲'),
            ('running', '运行中'),
            ('completed', '已完成'),
            ('failed', '失败'),
        ],
        default='idle',
        max_length=20,
        verbose_name='当前状态',
    )
    execution_count = models.IntegerField(default=0, verbose_name='执行次数')
    last_executed = models.DateTimeField(blank=True, null=True, verbose_name='最后执行时间')
    notify_on_success = models.BooleanField(default=False, verbose_name='成功时通知')
    notify_on_failure = models.BooleanField(default=True, verbose_name='失败时通知')
    notification_channels = models.JSONField(blank=True, default=list, verbose_name='通知渠道')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_test_tasks',
        verbose_name='创建者',
    )
    last_result = models.ForeignKey(
        TestResult,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='source_task',
        verbose_name='最后执行结果',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='test_tasks',
        verbose_name='所属项目',
    )

    class Meta:
        verbose_name = '测试任务'
        verbose_name_plural = '测试任务'
        db_table = 'qa_test_tasks'
        ordering = ['-created_at']


class PerformanceTestCase(models.Model):
    name = models.CharField(max_length=200, verbose_name='用例名称')
    description = models.TextField(blank=True, verbose_name='用例描述')
    url = models.CharField(max_length=1000, verbose_name='请求URL')
    method = models.CharField(
        choices=[
            ('GET', 'GET'),
            ('POST', 'POST'),
            ('PUT', 'PUT'),
            ('PATCH', 'PATCH'),
            ('DELETE', 'DELETE'),
        ],
        default='GET',
        max_length=10,
        verbose_name='请求方法',
    )
    headers = models.JSONField(blank=True, default=dict, verbose_name='请求头')
    body = models.TextField(blank=True, verbose_name='请求体')
    concurrent_users = models.IntegerField(default=10, verbose_name='并发用户数')
    duration_seconds = models.IntegerField(default=60, verbose_name='测试持续时间(秒)')
    ramp_up_seconds = models.IntegerField(default=10, verbose_name='预热时间(秒)')
    requests_per_second = models.IntegerField(blank=True, null=True, verbose_name='每秒请求数限制')
    expected_response_time_ms = models.IntegerField(default=1000, verbose_name='预期响应时间(ms)')
    expected_throughput = models.FloatField(blank=True, null=True, verbose_name='预期吞吐量(req/s)')
    expected_error_rate = models.FloatField(default=5.0, verbose_name='预期最大错误率(%)')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_performance_cases',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='performance_test_cases',
        verbose_name='所属项目',
    )
    related_tasks = models.ManyToManyField(
        Task,
        blank=True,
        related_name='linked_performance_test_cases',
        verbose_name='关联任务',
    )

    class Meta:
        verbose_name = '性能测试用例'
        verbose_name_plural = '性能测试用例'
        db_table = 'qa_performance_test_cases'
        ordering = ['-created_at']


class PerformanceTestResult(models.Model):
    total_requests = models.IntegerField(verbose_name='总请求数')
    successful_requests = models.IntegerField(verbose_name='成功请求数')
    failed_requests = models.IntegerField(verbose_name='失败请求数')
    avg_response_time_ms = models.FloatField(verbose_name='平均响应时间(ms)')
    min_response_time_ms = models.FloatField(verbose_name='最小响应时间(ms)')
    max_response_time_ms = models.FloatField(verbose_name='最大响应时间(ms)')
    p50_response_time_ms = models.FloatField(verbose_name='P50响应时间(ms)')
    p90_response_time_ms = models.FloatField(verbose_name='P90响应时间(ms)')
    p95_response_time_ms = models.FloatField(verbose_name='P95响应时间(ms)')
    p99_response_time_ms = models.FloatField(verbose_name='P99响应时间(ms)')
    throughput = models.FloatField(verbose_name='吞吐量(req/s)')
    error_rate = models.FloatField(verbose_name='错误率(%)')
    response_time_distribution = models.JSONField(blank=True, default=dict, verbose_name='响应时间分布')
    throughput_over_time = models.JSONField(blank=True, default=list, verbose_name='吞吐量时间序列')
    response_time_over_time = models.JSONField(blank=True, default=list, verbose_name='响应时间时间序列')
    error_details = models.JSONField(blank=True, default=list, verbose_name='错误详情')
    executed_at = models.DateTimeField(auto_now_add=True, verbose_name='执行时间')
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        verbose_name='执行者',
    )
    test_case = models.ForeignKey(
        'PerformanceTestCase',
        on_delete=models.CASCADE,
        related_name='results',
        verbose_name='测试用例',
    )
    test_result = models.OneToOneField(
        TestResult,
        on_delete=models.CASCADE,
        related_name='performance_details',
        verbose_name='关联测试结果',
    )

    class Meta:
        verbose_name = '性能测试结果'
        verbose_name_plural = '性能测试结果'
        db_table = 'qa_performance_test_results'
        ordering = ['-executed_at']


class ApiAutoTestSuite(models.Model):
    name = models.CharField(max_length=200, verbose_name='套件名称')
    description = models.TextField(blank=True, verbose_name='套件描述')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_auto_suites',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='api_auto_suites',
        verbose_name='所属项目',
    )

    class Meta:
        verbose_name = 'API自动化测试套件'
        verbose_name_plural = 'API自动化测试套件'
        db_table = 'qa_api_auto_suites'
        ordering = ['-created_at']


class ApiAutoTestResult(models.Model):
    name = models.CharField(max_length=200, verbose_name='执行名称')
    status = models.CharField(
        choices=[
            ('pending', '待执行'),
            ('running', '执行中'),
            ('passed', '通过'),
            ('failed', '失败'),
            ('error', '错误'),
        ],
        default='pending',
        max_length=20,
        verbose_name='执行状态',
    )
    total_cases = models.IntegerField(default=0, verbose_name='总用例数')
    passed_cases = models.IntegerField(default=0, verbose_name='通过数')
    failed_cases = models.IntegerField(default=0, verbose_name='失败数')
    error_cases = models.IntegerField(default=0, verbose_name='错误数')
    duration_ms = models.IntegerField(blank=True, null=True, verbose_name='执行时长(ms)')
    started_at = models.DateTimeField(blank=True, null=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='完成时间')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='executed_auto_tests',
        verbose_name='执行者',
    )
    suite = models.ForeignKey(
        ApiAutoTestSuite,
        on_delete=models.CASCADE,
        related_name='test_results',
        verbose_name='测试套件',
    )

    class Meta:
        verbose_name = 'API自动化测试结果'
        verbose_name_plural = 'API自动化测试结果'
        db_table = 'qa_api_auto_results'
        ordering = ['-created_at']


class ApiAutoTestCase(models.Model):
    name = models.CharField(max_length=200, verbose_name='用例名称')
    description = models.TextField(blank=True, verbose_name='用例描述')
    url = models.CharField(max_length=1000, verbose_name='请求URL')
    method = models.CharField(
        choices=[
            ('GET', 'GET'),
            ('POST', 'POST'),
            ('PUT', 'PUT'),
            ('PATCH', 'PATCH'),
            ('DELETE', 'DELETE'),
            ('HEAD', 'HEAD'),
            ('OPTIONS', 'OPTIONS'),
        ],
        default='GET',
        max_length=10,
        verbose_name='请求方法',
    )
    headers = models.JSONField(blank=True, default=dict, verbose_name='请求头')
    content_type = models.CharField(
        choices=[
            ('application/json', 'JSON'),
            ('application/x-www-form-urlencoded', 'Form'),
            ('multipart/form-data', 'Multipart'),
            ('text/plain', 'Text'),
        ],
        default='application/json',
        max_length=50,
        verbose_name='Content-Type',
    )
    body = models.TextField(blank=True, verbose_name='请求体')
    expected_status = models.IntegerField(blank=True, null=True, verbose_name='预期状态码')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    sort_order = models.IntegerField(default=0, verbose_name='排序顺序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    timeout_seconds = models.IntegerField(default=30, verbose_name='请求超时(秒)')
    form_files = models.JSONField(
        blank=True,
        default=list,
        help_text='[{name, filename, content, content_type, encoding?}]',
        verbose_name='上传文件',
    )
    query_params = models.JSONField(
        blank=True,
        default=dict,
        help_text='{k: v} 或 [[k, v], ...] 支持重复键',
        verbose_name='Query参数',
    )
    enable_cookie_session = models.BooleanField(
        default=True,
        help_text='True：与同计划/套件内的其它用例共享 Session；False：每次新开连接',
        verbose_name='复用Session Cookie',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_auto_cases',
        verbose_name='创建者',
    )
    suite = models.ForeignKey(
        ApiAutoTestSuite,
        on_delete=models.CASCADE,
        related_name='test_cases',
        verbose_name='所属套件',
    )

    class Meta:
        verbose_name = 'API自动化测试用例'
        verbose_name_plural = 'API自动化测试用例'
        db_table = 'qa_api_auto_cases'
        ordering = ['sort_order', '-created_at']


class ApiAutoTestCaseResult(models.Model):
    status_code = models.IntegerField(verbose_name='响应状态码')
    response_body = models.TextField(blank=True, verbose_name='响应体')
    response_headers = models.JSONField(default=dict, verbose_name='响应头')
    response_time_ms = models.IntegerField(verbose_name='响应时间(ms)')
    passed = models.BooleanField(verbose_name='是否通过')
    assertion_details = models.JSONField(default=list, verbose_name='断言详情')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    executed_at = models.DateTimeField(auto_now_add=True, verbose_name='执行时间')
    case = models.ForeignKey(
        ApiAutoTestCase,
        on_delete=models.CASCADE,
        related_name='case_results',
        verbose_name='测试用例',
    )
    test_result = models.ForeignKey(
        ApiAutoTestResult,
        on_delete=models.CASCADE,
        related_name='case_results',
        verbose_name='测试结果',
    )

    class Meta:
        verbose_name = 'API自动化用例执行结果'
        verbose_name_plural = 'API自动化用例执行结果'
        db_table = 'qa_api_auto_case_results'
        ordering = ['executed_at']


class ApiAutoTestAssertion(models.Model):
    assertion_type = models.CharField(
        choices=[
            ('status_code', '状态码断言'),
            ('json_equals', 'JSON字段值断言'),
            ('json_exists', 'JSON字段存在断言'),
            ('json_contains', 'JSON字段包含断言'),
            ('response_time', '响应时间断言'),
        ],
        max_length=20,
        verbose_name='断言类型',
    )
    json_path = models.CharField(
        blank=True,
        help_text='例如: data.user.name 或 result[0].id',
        max_length=500,
        verbose_name='JSON路径',
    )
    expected_value = models.CharField(
        blank=True,
        help_text='期望的值或表达式',
        max_length=1000,
        verbose_name='预期值',
    )
    comparison_operator = models.CharField(
        default='eq',
        help_text='eq(等于), ne(不等于), gt(大于), gte(大于等于), lt(小于), lte(小于等于), contains(包含)',
        max_length=10,
        verbose_name='比较操作符',
    )
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    error_message = models.CharField(blank=True, max_length=500, verbose_name='失败时的错误信息')
    sort_order = models.IntegerField(default=0, verbose_name='排序顺序')
    case = models.ForeignKey(
        ApiAutoTestCase,
        on_delete=models.CASCADE,
        related_name='assertions',
        verbose_name='所属用例',
    )

    class Meta:
        verbose_name = 'API自动化测试断言'
        verbose_name_plural = 'API自动化测试断言'
        db_table = 'qa_api_auto_assertions'
        ordering = ['sort_order', 'id']


class ApiAutoTestExtractor(models.Model):
    name = models.CharField(max_length=100, verbose_name='变量名')
    source = models.CharField(
        choices=[
            ('body', '响应体 JSON'),
            ('header', '响应头'),
            ('status', '状态码'),
            ('cookie', 'Cookie'),
            ('response_time', '响应时间(ms)'),
        ],
        default='body',
        max_length=20,
        verbose_name='来源',
    )
    expression = models.CharField(
        blank=True,
        help_text='body: JSONPath; header/cookie: 名称; status/response_time: 留空',
        max_length=500,
        verbose_name='表达式',
    )
    default_value = models.CharField(
        blank=True,
        help_text='抽取失败时使用，避免后续 case 拿到 None',
        max_length=500,
        verbose_name='默认值',
    )
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    sort_order = models.IntegerField(default=0, verbose_name='排序顺序')
    case = models.ForeignKey(
        ApiAutoTestCase,
        on_delete=models.CASCADE,
        related_name='extractors',
        verbose_name='所属用例',
    )

    class Meta:
        verbose_name = 'API自动化变量抽取器'
        verbose_name_plural = 'API自动化变量抽取器'
        db_table = 'qa_api_auto_extractors'
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['case', 'is_active'], name='qa_api_auto_case_id_ccb96c_idx'),
        ]


class CiCdConfig(models.Model):
    name = models.CharField(max_length=255, verbose_name='配置名称')
    ci_type = models.CharField(
        choices=[
            ('jenkins', 'Jenkins'),
            ('gitlab', 'GitLab CI'),
            ('github', 'GitHub Actions'),
        ],
        max_length=20,
        verbose_name='CI类型',
    )
    webhook_url = models.URLField(blank=True, verbose_name='Webhook URL')
    api_token = models.CharField(blank=True, max_length=255, verbose_name='API Token')
    branch = models.CharField(default='main', max_length=100, verbose_name='监听分支')
    auto_trigger = models.BooleanField(default=False, verbose_name='自动触发')
    test_suite_ids = models.JSONField(default=list, verbose_name='关联测试套件')
    headers = models.JSONField(default=dict, verbose_name='自定义请求头')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_cicd_configs',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='cicd_configs',
        verbose_name='所属项目',
    )

    class Meta:
        verbose_name = 'CI/CD配置'
        verbose_name_plural = 'CI/CD配置'
        db_table = 'qa_cicd_config'
        ordering = ['-created_at']


class PipelineRun(models.Model):
    status = models.CharField(
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('passed', 'Passed'),
            ('failed', 'Failed'),
        ],
        default='pending',
        max_length=20,
        verbose_name='状态',
    )
    commit_sha = models.CharField(blank=True, max_length=40, verbose_name='提交SHA')
    branch = models.CharField(blank=True, max_length=100, verbose_name='分支')
    log_output = models.TextField(blank=True, verbose_name='执行日志')
    test_results_summary = models.JSONField(default=dict, verbose_name='测试结果摘要')
    started_at = models.DateTimeField(null=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, verbose_name='完成时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    cicd_config = models.ForeignKey(
        CiCdConfig,
        on_delete=models.CASCADE,
        related_name='pipeline_runs',
        verbose_name='CI/CD配置',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='pipeline_runs',
        verbose_name='所属项目',
    )

    class Meta:
        verbose_name = 'Pipeline执行记录'
        verbose_name_plural = 'Pipeline执行记录'
        db_table = 'qa_pipeline_run'
        ordering = ['-created_at']


class TestEnvironment(models.Model):
    name = models.CharField(max_length=100, verbose_name='环境名称')
    base_url = models.CharField(blank=True, max_length=500, verbose_name='Base URL')
    variables = models.JSONField(blank=True, default=dict, verbose_name='环境变量')
    description = models.TextField(blank=True, verbose_name='描述')
    is_default = models.BooleanField(default=False, verbose_name='是否为默认环境')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_test_environments',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='test_environments',
        verbose_name='所属项目',
    )

    class Meta:
        verbose_name = '测试环境'
        verbose_name_plural = '测试环境'
        db_table = 'qa_test_environments'
        ordering = ['project', '-is_default', 'name']
        indexes = [
            models.Index(fields=['project', 'is_default'], name='qa_test_env_project_e67b63_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=('project', 'name'), name='uniq_env_per_project_name'),
        ]


class TestRunPlan(models.Model):
    name = models.CharField(max_length=200, verbose_name='计划名称')
    description = models.TextField(blank=True, verbose_name='描述')
    case_ids = models.JSONField(default=list, verbose_name='用例ID列表')
    parallel = models.BooleanField(default=False, verbose_name='并发执行')
    max_workers = models.IntegerField(default=4, verbose_name='最大并发数')
    stop_on_failure = models.BooleanField(default=False, verbose_name='遇错中止')
    case_timeout_seconds = models.IntegerField(default=30, verbose_name='单用例超时(秒)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    environment = models.ForeignKey(
        TestEnvironment,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='run_plans',
        verbose_name='运行环境',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_run_plans',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='test_run_plans',
        verbose_name='所属项目',
    )

    class Meta:
        verbose_name = '批量执行计划'
        verbose_name_plural = '批量执行计划'
        db_table = 'qa_test_run_plans'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at'], name='qa_test_run_project_c797d3_idx'),
        ]


class TestGlobalVar(models.Model):
    key = models.CharField(max_length=100, verbose_name='变量名')
    value = models.TextField(blank=True, verbose_name='变量值')
    description = models.CharField(blank=True, max_length=255, verbose_name='说明')
    is_secret = models.BooleanField(default=False, verbose_name='是否敏感（前端脱敏）')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_test_global_vars',
        verbose_name='创建者',
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='test_global_vars',
        verbose_name='所属项目',
    )

    class Meta:
        verbose_name = '测试全局变量'
        verbose_name_plural = '测试全局变量'
        db_table = 'qa_test_global_vars'
        ordering = ['project', 'key']
        constraints = [
            models.UniqueConstraint(fields=('project', 'key'), name='uniq_global_var_per_project_key'),
        ]


class TestRun(models.Model):
    """一次批量执行(父任务)"""
    STATUS = [
        ('pending', '待执行'), ('running', '执行中'),
        ('passed', '全部通过'), ('failed', '有失败'),
        ('error', '执行异常'), ('cancelled', '已取消'),
    ]
    TRIGGER = [
        ('manual', '手动'), ('scheduled', '定时'),
        ('cicd', 'CI/CD'), ('regression', '回归'),
    ]
    TEST_TYPE = [
        ('api', 'API'), ('ui', 'UI'),
        ('performance', '性能'), ('mixed', '混合'),
    ]

    project = models.ForeignKey(
        'room.Project', on_delete=models.CASCADE, related_name='test_runs'
    )
    name = models.CharField(max_length=200)
    trigger = models.CharField(max_length=20, choices=TRIGGER, default='manual')
    test_type = models.CharField(max_length=20, choices=TEST_TYPE, default='api')
    status = models.CharField(max_length=20, choices=STATUS, default='pending')

    total_count = models.IntegerField(default=0)
    passed_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    duration_ms = models.IntegerField(null=True)

    config_snapshot = models.JSONField(default=dict, blank=True)
    curl_template = models.TextField(blank=True)

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name='triggered_test_runs',
    )
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'qa_test_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['status']),
        ]
        verbose_name = '测试运行'
        verbose_name_plural = '测试运行'

    def __str__(self):
        return f"{self.name} [{self.status}]"

    # 运行时标记槽位:不写 DB。当前 finalizer 通过重读 DB status 来识别 cancel,
    # 此属性保留作为未来协作式取消(让运行中的 worker 主动停下)的信号位。
    cancelled = False

    def recompute_pass_rate(self):
        completed = self.passed_count + self.failed_count + self.error_count
        self.pass_rate = (
            round(self.passed_count / completed * 100, 2)
            if completed > 0 else 0
        )


class TestRunCaseResult(models.Model):
    """批量执行里单条用例的结果"""
    STATUS = [
        ('pending', '待执行'), ('running', '执行中'),
        ('passed', '通过'), ('failed', '失败'),
        ('error', '异常'), ('skipped', '跳过'),
    ]
    CASE_TYPE = [
        ('api', 'API'), ('ui', 'UI'), ('performance', '性能'),
    ]

    test_run = models.ForeignKey(
        TestRun, on_delete=models.CASCADE, related_name='case_results'
    )
    case_type = models.CharField(max_length=20, choices=CASE_TYPE, default='api')
    sequence = models.IntegerField()

    api_test_case = models.ForeignKey(
        'ApiTestCase', null=True, on_delete=models.SET_NULL,
        related_name='run_case_results',
    )
    ui_test_case = models.ForeignKey(
        'UiTestCase', null=True, on_delete=models.SET_NULL,
        related_name='run_case_results',
    )

    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    duration_ms = models.IntegerField(null=True)
    status_code = models.IntegerField(null=True)
    response_body = models.TextField(blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    assertion_results = models.JSONField(default=list, blank=True)
    request_snapshot = models.JSONField(default=dict, blank=True)
    curl = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    legacy_api_result_id = models.IntegerField(null=True)
    legacy_test_result_id = models.IntegerField(null=True)

    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = 'qa_test_run_case_results'
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(
                fields=['test_run', 'sequence'],
                name='uniq_test_run_sequence',
            ),
        ]
        indexes = [
            models.Index(fields=['test_run', 'status']),
            models.Index(fields=['api_test_case', '-completed_at']),
        ]
        verbose_name = '测试运行用例结果'
        verbose_name_plural = '测试运行用例结果'

    def __str__(self):
        return f"#{self.sequence} {self.status}"
