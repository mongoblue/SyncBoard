"""质量报告端点测试"""
import pytest
from django.contrib.auth.models import User
from bug_tracker.models import Bug


@pytest.mark.django_db
class TestQualityReportBugDensity:
    def test_uses_bug_model_not_task_tag(self, auth_client, test_project, test_user):
        # 给项目创建一个 Bug
        Bug.objects.create(
            project=test_project, title='T1', reporter=test_user,
            severity='major', priority='p2', status='new',
        )
        # 给项目造一个名为 'bug' 的 Tag 但不挂 task —— 不应影响 bug_count
        from room.models import Tag
        Tag.objects.create(project=test_project, name='bug', color='#f00')

        resp = auth_client.get(f'/api/qa/devops/quality-report/?project_id={test_project.id}')
        assert resp.status_code == 200
        data = resp.json()
        # summary.bug_count 必须来自 bug_tracker.Bug
        assert data['summary']['bug_count'] == 1
        # dimensions 中 Bug密度 的 detail 文本应反映 1 个 Bug
        bug_dim = next(d for d in data['dimensions'] if d['name'] == 'Bug密度')
        assert '1 个 Bug' in bug_dim['detail']

    def test_zero_bugs_zero_density(self, auth_client, test_project):
        resp = auth_client.get(f'/api/qa/devops/quality-report/?project_id={test_project.id}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['summary']['bug_count'] == 0
        bug_dim = next(d for d in data['dimensions'] if d['name'] == 'Bug密度')
        assert bug_dim['score'] == 20  # 0% 密度 → 满分

    def test_quality_report_uses_performance_result_p95_response_time_ms(self, auth_client, test_project, test_user):
        from qa_center.models import PerformanceTestCase, PerformanceTestResult, TestResult

        case = PerformanceTestCase.objects.create(
            name='perf-case',
            url='https://example.com/api/foo',
            method='GET',
            project=test_project,
            created_by=test_user,
        )
        result = TestResult.objects.create(
            test_type='performance',
            name=case.name,
            project=test_project,
            status='passed',
            executed_by=test_user,
        )
        PerformanceTestResult.objects.create(
            test_case=case,
            test_result=result,
            executed_by=test_user,
            total_requests=100,
            successful_requests=100,
            failed_requests=0,
            avg_response_time_ms=100.0,
            min_response_time_ms=50.0,
            max_response_time_ms=250.0,
            p50_response_time_ms=90.0,
            p90_response_time_ms=150.0,
            p95_response_time_ms=320.0,
            p99_response_time_ms=600.0,
            throughput=20.0,
            error_rate=0.0,
        )

        resp = auth_client.get(f'/api/qa/devops/quality-report/?project_id={test_project.id}')

        assert resp.status_code == 200
        data = resp.json()
        perf_dim = next(d for d in data['dimensions'] if d['name'] == '性能指标')
        assert perf_dim['score'] == 20
        assert perf_dim['detail'] == 'P95: 320ms'
        assert data['summary']['has_perf_data'] is True
