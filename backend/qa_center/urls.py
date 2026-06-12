from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DataFactoryView, RunTestView
from .views_api_test import ApiTestCaseViewSet, ApiTestResultViewSet, ApiTestCaseBatchRunView
from .views_ui_test import UiTestCaseViewSet
from .views_test_result import TestResultViewSet
from .views_performance import PerformanceTestCaseViewSet, PerformanceTestResultViewSet
from .views_api_auto_test import (
    ApiAutoTestSuiteViewSet,
    ApiAutoTestCaseViewSet,
    ApiAutoTestAssertionViewSet,
    ApiAutoTestResultViewSet,
    ApiAutoTestCaseResultViewSet,
    ApiAutoTestExecuteView,
    ApiAutoTestExtractorViewSet,
)
from .views_test_link import TestCaseLinkTaskView, TestCaseUnlinkTaskView
from .views_devops import (
    DashboardStatsView,
    RecentExecutionsView,
    CiCdIntegrationView,
    TestTaskView,
    TestTaskExecuteView,
    TestTaskStatusView,
    TestTaskHistoryView,
    QuickTestView,
    PipelineRunListView,
    PipelineRunDetailView,
    PipelineRunTriggerView,
    PipelineRunWebhookView,
    ProjectQualityReportView,
)
from .views_run_plan import TestRunPlanViewSet
from .views_environment import TestEnvironmentViewSet, TestGlobalVarViewSet
from .views_test_run import (
    cancel_test_run,
    list_test_runs,
    test_run_detail,
    test_run_cases,
    test_run_case_detail,
    rerun_test_run,
)

router = DefaultRouter()
router.register(r'api-cases', ApiTestCaseViewSet, basename='api_test_case')
router.register(r'api-results', ApiTestResultViewSet, basename='api_test_result')
router.register(r'ui-cases', UiTestCaseViewSet, basename='ui_test_case')
router.register(r'test-results', TestResultViewSet, basename='test_result')
router.register(r'performance-cases', PerformanceTestCaseViewSet, basename='performance_test_case')
router.register(r'performance-results', PerformanceTestResultViewSet, basename='performance_test_result')
router.register(r'auto-suites', ApiAutoTestSuiteViewSet, basename='api_auto_suite')
router.register(r'auto-cases', ApiAutoTestCaseViewSet, basename='api_auto_case')
router.register(r'auto-assertions', ApiAutoTestAssertionViewSet, basename='api_auto_assertion')
router.register(r'auto-extractors', ApiAutoTestExtractorViewSet, basename='api_auto_extractor')
router.register(r'auto-results', ApiAutoTestResultViewSet, basename='api_auto_result')
router.register(r'auto-case-results', ApiAutoTestCaseResultViewSet, basename='api_auto_case_result')
router.register(r'run-plans', TestRunPlanViewSet, basename='test_run_plan')
router.register(r'environments', TestEnvironmentViewSet, basename='test_environment')
router.register(r'global-vars', TestGlobalVarViewSet, basename='test_global_var')

urlpatterns = [
    path('data-factory/', DataFactoryView.as_view(), name='data_factory'),
    path('run-test/', RunTestView.as_view(), name='run_test'),
    path('api-cases/run-batch/', ApiTestCaseBatchRunView.as_view(), name='api_case_run_batch'),
    path('runs/<int:run_id>/cancel/', cancel_test_run, name='test_run_cancel'),
    path('runs/<int:run_id>/rerun/', rerun_test_run, name='test_run_rerun'),
    path('runs/', list_test_runs, name='test_run_list'),
    path('runs/<int:run_id>/', test_run_detail, name='test_run_detail'),
    path('runs/<int:run_id>/cases/', test_run_cases, name='test_run_cases'),
    path('runs/<int:run_id>/cases/<int:case_result_id>/', test_run_case_detail, name='test_run_case_detail'),
    path('', include(router.urls)),
    path('auto-execute/', ApiAutoTestExecuteView.as_view(), name='api_auto_execute'),
    path('devops/stats/', DashboardStatsView.as_view(), name='devops_stats'),
    path('devops/recent-executions/', RecentExecutionsView.as_view(), name='devops_recent_executions'),
    path('devops/cicd-config/', CiCdIntegrationView.as_view(), name='devops_cicd_config'),
    path('devops/cicd-config/<int:config_id>/', CiCdIntegrationView.as_view(), name='devops_cicd_config_detail'),
    path('devops/tasks/', TestTaskView.as_view(), name='devops_tasks'),
    path('devops/tasks/<int:task_id>/', TestTaskView.as_view(), name='devops_task_detail'),
    path('devops/tasks/<int:task_id>/execute/', TestTaskExecuteView.as_view(), name='devops_task_execute'),
    path('devops/tasks/<int:task_id>/status/', TestTaskStatusView.as_view(), name='devops_task_status'),
    path('devops/tasks/<int:task_id>/history/', TestTaskHistoryView.as_view(), name='devops_task_history'),
    path('link-task/', TestCaseLinkTaskView.as_view(), name='test_link_task'),
    path('unlink-task/', TestCaseUnlinkTaskView.as_view(), name='test_unlink_task'),
    path('devops/pipeline-runs/', PipelineRunListView.as_view(), name='pipeline_run_list'),
    path('devops/pipeline-runs/<int:run_id>/', PipelineRunDetailView.as_view(), name='pipeline_run_detail'),
    path('devops/quality-report/', ProjectQualityReportView.as_view(), name='quality_report'),
    path('devops/cicd-config/<int:config_id>/trigger/', PipelineRunTriggerView.as_view(), name='cicd_trigger'),
    path('devops/cicd-config/<int:config_id>/webhook/', PipelineRunWebhookView.as_view(), name='cicd_webhook'),
    path('devops/quick-test/', QuickTestView.as_view(), name='devops_quick_test'),
]