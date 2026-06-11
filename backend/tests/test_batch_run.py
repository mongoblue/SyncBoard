"""Phase 5: 批量执行 run-batch 端点 + cancel 端点测试"""
import json
import time
import pytest
from rest_framework.test import APIClient
from qa_center.models import ApiTestCase, TestRun, TestRunCaseResult


@pytest.fixture
def batch_auth_client(db, test_user):
    """复用 conftest 的 test_user,使用 APIClient(避免与 conftest 的 auth_client 重名)"""
    client = APIClient()
    client.force_authenticate(user=test_user)
    return client, test_user


@pytest.fixture
def five_cases(db, test_project, test_user):
    return [
        ApiTestCase.objects.create(
            name=f'case{i}', url=f'/health/', method='GET',
            expected_status=200, project=test_project, created_by=test_user,
            expected_response={'assertions': []},
        )
        for i in range(5)
    ]


@pytest.mark.django_db
def test_run_batch_returns_run_id_immediately(batch_auth_client, five_cases):
    client, _ = batch_auth_client
    response = client.post(
        '/api/qa/api-cases/run-batch/',
        data=json.dumps({
            'case_ids': [c.id for c in five_cases],
            'name': 'batch1',
            'max_workers': 1,
        }),
        content_type='application/json',
    )
    assert response.status_code == 202
    data = response.json()
    assert 'run_id' in data
    run = TestRun.objects.get(id=data['run_id'])
    assert run.total_count == 5
    assert run.name == 'batch1'


@pytest.mark.django_db(transaction=True)
def test_run_batch_creates_one_case_result_per_case(batch_auth_client, five_cases):
    client, _ = batch_auth_client
    response = client.post(
        '/api/qa/api-cases/run-batch/',
        data=json.dumps({
            'case_ids': [c.id for c in five_cases],
            'max_workers': 1,
        }),
        content_type='application/json',
    )
    run_id = response.json()['run_id']
    # 等待后台执行完成
    for _ in range(60):
        run = TestRun.objects.get(id=run_id)
        if run.status != 'running':
            break
        time.sleep(0.3)
    results = TestRunCaseResult.objects.filter(test_run_id=run_id).order_by('sequence')
    assert results.count() == 5
    assert {r.sequence for r in results} == {1, 2, 3, 4, 5}


@pytest.mark.django_db(transaction=True)
def test_run_batch_updates_counts(batch_auth_client, five_cases):
    client, _ = batch_auth_client
    response = client.post(
        '/api/qa/api-cases/run-batch/',
        data=json.dumps({
            'case_ids': [c.id for c in five_cases],
            'max_workers': 1,
        }),
        content_type='application/json',
    )
    run_id = response.json()['run_id']
    for _ in range(60):
        run = TestRun.objects.get(id=run_id)
        if run.status != 'running':
            break
        time.sleep(0.3)
    run = TestRun.objects.get(id=run_id)
    assert run.passed_count + run.failed_count + run.error_count == 5
