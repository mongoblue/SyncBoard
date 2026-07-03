"""Phase 6: TestRun REST 端点 (list / detail / cases / case_detail) 测试。

P1 重构后：legacy API 用例模型已删除，rerun 端点返回 410 Gone。
"""
import pytest
from rest_framework.test import APIClient
from qa_center.models import TestRun, TestRunCaseResult, ApiAutoTestCase


@pytest.fixture
def tr_auth_client(db, test_user):
    """复用 conftest 的 test_user,使用 APIClient(避免与 conftest 的 auth_client 重名)"""
    client = APIClient()
    client.force_authenticate(user=test_user)
    return client, test_user


@pytest.fixture
def two_runs(db, test_project, tr_auth_client):
    _, user = tr_auth_client
    case = ApiAutoTestCase.objects.create(
        name='c1', url='/api/x', method='GET', expected_status=200,
        project=test_project, created_by=user,
    )
    r1 = TestRun.objects.create(
        project=test_project, name='run1', test_type='api', status='passed',
        total_count=1, passed_count=1, failed_count=0, error_count=0,
        pass_rate=100.0,
    )
    TestRunCaseResult.objects.create(
        test_run=r1, case_type='api', sequence=1, api_auto_case=case,
        status='passed',
        result_metadata={
            'provider': 'http',
            'expectation_type': 'success_response',
            'default_assertion_policy': 'success_response',
            'expected_status': 200,
            'semantic_status': 'success_response_passed',
            'semantic_label': '成功响应断言通过',
        },
    )
    r2 = TestRun.objects.create(
        project=test_project, name='run2', test_type='api', status='failed',
        total_count=2, passed_count=1, failed_count=1, error_count=0,
        pass_rate=50.0,
    )
    TestRunCaseResult.objects.create(
        test_run=r2, case_type='api', sequence=1, api_auto_case=case,
        status='passed',
        result_metadata={
            'provider': 'http',
            'expectation_type': 'success_response',
            'default_assertion_policy': 'success_response',
            'expected_status': 200,
            'semantic_status': 'success_response_passed',
            'semantic_label': '成功响应断言通过',
        },
    )
    TestRunCaseResult.objects.create(
        test_run=r2, case_type='api', sequence=2, api_auto_case=case,
        status='failed', status_code=500,
        result_metadata={
            'provider': 'http',
            'expectation_type': 'error_response',
            'default_assertion_policy': 'expected_error_response',
            'expected_status': 404,
            'semantic_status': 'expected_error_unmatched',
            'semantic_label': '预期错误响应但未匹配',
        },
    )
    return r1, r2, case


@pytest.mark.django_db
def test_list_runs(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    r1, _, _ = two_runs
    response = client.get(f'/api/qa/runs/?project={r1.project_id}')
    assert response.status_code == 200
    data = response.json()
    assert 'results' in data
    assert data['count'] == 2
    names = {r['name'] for r in data['results']}
    assert {'run1', 'run2'} == names


@pytest.mark.django_db
def test_list_runs_filter_by_status(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    r1, _, _ = two_runs
    response = client.get(f'/api/qa/runs/?project={r1.project_id}&status=failed')
    assert response.status_code == 200
    data = response.json()
    assert data['count'] == 1
    assert data['results'][0]['status'] == 'failed'


@pytest.mark.django_db
def test_run_detail(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    r1, _, _ = two_runs
    response = client.get(f'/api/qa/runs/{r1.id}/')
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == r1.id
    assert data['name'] == 'run1'
    assert data['total_count'] == 1
    assert data['passed_count'] == 1


@pytest.mark.django_db
def test_run_cases_list(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    _, r2, _ = two_runs
    response = client.get(f'/api/qa/runs/{r2.id}/cases/')
    assert response.status_code == 200
    data = response.json()
    assert data['count'] == 2
    statuses = {c['status'] for c in data['results']}
    assert statuses == {'passed', 'failed'}


@pytest.mark.django_db
def test_run_cases_include_semantic_fields(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    _, r2, _ = two_runs
    response = client.get(f'/api/qa/runs/{r2.id}/cases/')
    assert response.status_code == 200
    data = response.json()
    failed = next(c for c in data['results'] if c['status'] == 'failed')
    assert failed['expectation_type'] == 'error_response'
    assert failed['semantic_status'] == 'expected_error_unmatched'
    assert failed['semantic_label'] == '预期错误响应但未匹配'
    assert failed['expected_status'] == 404


@pytest.mark.django_db
def test_run_case_detail(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    _, r2, _ = two_runs
    case_result = r2.case_results.get(sequence=2)
    response = client.get(f'/api/qa/runs/{r2.id}/cases/{case_result.id}/')
    assert response.status_code == 200
    data = response.json()
    assert data['sequence'] == 2
    assert data['status'] == 'failed'
    assert data['status_code'] == 500
    assert 'curl' in data


@pytest.mark.django_db
def test_run_case_detail_includes_semantic_fields(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    _, r2, _ = two_runs
    case_result = r2.case_results.get(sequence=2)
    response = client.get(f'/api/qa/runs/{r2.id}/cases/{case_result.id}/')
    assert response.status_code == 200
    data = response.json()
    assert data['expectation_type'] == 'error_response'
    assert data['semantic_status'] == 'expected_error_unmatched'
    assert data['semantic_label'] == '预期错误响应但未匹配'
    assert data['expected_status'] == 404


@pytest.mark.django_db
def test_list_runs_invalid_page_returns_400(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    response = client.get('/api/qa/runs/?page=abc')
    assert response.status_code == 400


@pytest.mark.django_db
def test_rerun_returns_410_deprecated(tr_auth_client, two_runs):
    """P1：legacy API 用例重跑已废弃，返回 410 Gone。"""
    client, _ = tr_auth_client
    _, r2, _ = two_runs
    response = client.post(f'/api/qa/runs/{r2.id}/rerun/')
    assert response.status_code == 410
    data = response.json()
    assert data.get('error_code') == 'rerun_deprecated'


@pytest.mark.django_db
def test_rerun_404_when_run_missing(tr_auth_client):
    client, _ = tr_auth_client
    response = client.post('/api/qa/runs/999999/rerun/')
    assert response.status_code == 404


@pytest.mark.django_db
def test_rerun_410_for_empty_run(tr_auth_client, test_project):
    """P1：空 run 重跑也返回 410（rerun 整体已废弃）。"""
    client, _ = tr_auth_client
    empty_run = TestRun.objects.create(
        project=test_project, name='empty', test_type='api', status='passed',
        total_count=0, passed_count=0, failed_count=0, error_count=0,
    )
    response = client.post(f'/api/qa/runs/{empty_run.id}/rerun/')
    assert response.status_code == 410


@pytest.mark.django_db
def test_rerun_410_for_running_run(tr_auth_client, test_project):
    """P1：running 状态的 run 重跑也返回 410。"""
    client, _ = tr_auth_client
    running_run = TestRun.objects.create(
        project=test_project, name='running', test_type='api', status='running',
        total_count=1, passed_count=0, failed_count=0, error_count=0,
    )
    response = client.post(f'/api/qa/runs/{running_run.id}/rerun/')
    assert response.status_code == 410
