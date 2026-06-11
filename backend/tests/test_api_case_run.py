"""单条 API 用例 run 端点测试"""
import json
import pytest
from qa_center.models import (
    ApiTestCase, TestRun, TestRunCaseResult, ApiTestResult,
)
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from room.models import Project


@pytest.fixture
def api_auth_client(db):
    user = User.objects.create_user(username='api_tester', password='pass')
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def api_project(db, api_auth_client):
    _, user = api_auth_client
    return Project.objects.create(name='Test Project', owner=user)


@pytest.mark.django_db
def test_single_run_extracts_response_variables(api_auth_client, api_project):
    """Task 9.6: response_extractions 应该在 assertion_results 末尾产出 extractions 块"""
    client, user = api_auth_client
    case = ApiTestCase.objects.create(
        name='health', url='/health/', method='GET',
        expected_status=200, project=api_project, created_by=user,
        expected_response={'assertions': []},
        response_extractions=[
            {'json_path': '$.status', 'var_name': 'health_status', 'default': None},
        ],
    )
    response = client.post(
        f'/api/qa/api-cases/{case.id}/run/',
        data=json.dumps({'body': None}),
        content_type='application/json',
    )
    assert response.status_code == 200
    data = response.json()
    # assertion_results 末尾应该有 extractions 块
    assert any(isinstance(r, dict) and 'extractions' in r for r in data['assertion_results'])
    # 找出 extractions 块,确认 health_status 被抽取出来
    ext_block = next(r for r in data['assertion_results'] if isinstance(r, dict) and 'extractions' in r)
    names = [it['name'] for it in ext_block['extractions']]
    assert 'health_status' in names


@pytest.mark.django_db
def test_single_run_creates_test_run(api_auth_client, api_project):
    """Task 10/11: 单条 run 应该双写 TestRun 并返回 run_id / case_result_id / curl"""
    client, user = api_auth_client
    case = ApiTestCase.objects.create(
        name='login', url='/api/auth/login/', method='POST',
        expected_status=200, project=api_project, created_by=user,
        expected_response={'assertions': []},
    )
    response = client.post(
        f'/api/qa/api-cases/{case.id}/run/',
        data=json.dumps({'body': None}),
        content_type='application/json',
    )
    assert response.status_code == 200
    data = response.json()
    assert 'run_id' in data
    assert 'case_result_id' in data
    assert 'curl' in data

    run = TestRun.objects.get(id=data['run_id'])
    assert run.project == api_project
    assert run.test_type == 'api'
    assert run.total_count == 1

    case_result = TestRunCaseResult.objects.get(id=data['case_result_id'])
    assert case_result.test_run == run
    assert case_result.api_test_case == case
    assert case_result.sequence == 1
    # legacy 字段有填
    assert case_result.legacy_api_result_id is not None


@pytest.mark.django_db
def test_single_run_response_curl_omits_cookie(api_auth_client, api_project):
    """Task 11: 返回的 curl 不应该含 Cookie 头"""
    client, user = api_auth_client
    case = ApiTestCase.objects.create(
        name='health', url='/health/', method='GET',
        expected_status=200, project=api_project, created_by=user,
        expected_response={'assertions': []},
    )
    response = client.post(
        f'/api/qa/api-cases/{case.id}/run/',
        data=json.dumps({'body': None}),
        content_type='application/json',
    )
    data = response.json()
    assert 'Cookie' not in data['curl']
    assert 'curl -X GET' in data['curl']
