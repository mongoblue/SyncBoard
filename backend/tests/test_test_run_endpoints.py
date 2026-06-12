"""Phase 6: TestRun REST 端点 (list / detail / cases / case_detail) 测试"""
import pytest
from rest_framework.test import APIClient
from qa_center.models import TestRun, TestRunCaseResult, ApiTestCase


@pytest.fixture
def tr_auth_client(db, test_user):
    """复用 conftest 的 test_user,使用 APIClient(避免与 conftest 的 auth_client 重名)"""
    client = APIClient()
    client.force_authenticate(user=test_user)
    return client, test_user


@pytest.fixture
def two_runs(db, test_project, tr_auth_client):
    _, user = tr_auth_client
    case = ApiTestCase.objects.create(
        name='c1', url='/api/x', method='GET', expected_status=200,
        project=test_project, created_by=user,
        expected_response={'assertions': []},
    )
    r1 = TestRun.objects.create(
        project=test_project, name='run1', test_type='api', status='passed',
        total_count=1, passed_count=1, failed_count=0, error_count=0,
        pass_rate=100.0,
    )
    TestRunCaseResult.objects.create(
        test_run=r1, case_type='api', sequence=1, api_test_case=case,
        status='passed',
    )
    r2 = TestRun.objects.create(
        project=test_project, name='run2', test_type='api', status='failed',
        total_count=2, passed_count=1, failed_count=1, error_count=0,
        pass_rate=50.0,
    )
    TestRunCaseResult.objects.create(
        test_run=r2, case_type='api', sequence=1, api_test_case=case,
        status='passed',
    )
    TestRunCaseResult.objects.create(
        test_run=r2, case_type='api', sequence=2, api_test_case=case,
        status='failed', status_code=500,
    )
    return r1, r2, case


@pytest.mark.django_db
def test_list_runs(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    r1, r2, _ = two_runs
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
def test_list_runs_invalid_page_returns_400(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    response = client.get('/api/qa/runs/?page=abc')
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_rerun_creates_new_test_run(tr_auth_client, two_runs):
    client, _ = tr_auth_client
    _, r2, case = two_runs
    # r2 在 fixture 中没设 config_snapshot,走 case_results.api_test_case 兜底分支
    response = client.post(f'/api/qa/runs/{r2.id}/rerun/')
    assert response.status_code == 202
    data = response.json()
    assert 'new_run_id' in data
    new_run = TestRun.objects.get(id=data['new_run_id'])
    assert new_run.config_snapshot.get('rerun_from') == r2.id
    # case_ids 写进了 config_snapshot
    assert case.id in new_run.config_snapshot.get('case_ids', [])
    # 新 run 至少有 1 个 case
    assert new_run.total_count >= 1


@pytest.mark.django_db
def test_rerun_404_when_run_missing(tr_auth_client):
    client, _ = tr_auth_client
    response = client.post('/api/qa/runs/999999/rerun/')
    assert response.status_code == 404


@pytest.mark.django_db
def test_rerun_400_when_no_cases(tr_auth_client, test_project):
    """原 run 既无 config_snapshot.case_ids 也无 case_results,应 400。"""
    client, _ = tr_auth_client
    empty_run = TestRun.objects.create(
        project=test_project, name='empty', test_type='api', status='passed',
        total_count=0, passed_count=0, failed_count=0, error_count=0,
    )
    response = client.post(f'/api/qa/runs/{empty_run.id}/rerun/')
    assert response.status_code == 400
