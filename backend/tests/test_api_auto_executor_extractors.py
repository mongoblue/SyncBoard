import json
from unittest.mock import Mock, patch

import pytest

from qa_center.models import (
    ApiAutoTestCase,
    ApiAutoTestExtractor,
    ApiAutoTestSuite,
    TestEnvironment,
)
from qa_center.api_auto_executor import run_api_auto_test


class _FakeElapsed:
    def total_seconds(self):
        return 0.123


def _fake_response(payload, status_code=200, headers=None, text=None, cookies=None):
    response = Mock()
    response.status_code = status_code
    response.headers = headers or {'Content-Type': 'application/json'}
    response.text = text if text is not None else json.dumps(payload)
    response.elapsed = _FakeElapsed()
    response.cookies = cookies or {}
    response.json.return_value = payload
    return response


@pytest.mark.django_db
def test_api_auto_executor_propagates_extracted_variable_to_later_case(test_project, test_user):
    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        name='extractor suite',
        created_by=test_user,
    )
    login_case = ApiAutoTestCase.objects.create(
        suite=suite,
        name='login',
        method='GET',
        url='https://example.com/login',
        expected_status=200,
        sort_order=1,
        created_by=test_user,
    )
    ApiAutoTestExtractor.objects.create(
        case=login_case,
        name='token',
        source='body',
        expression='token',
        sort_order=1,
    )
    ApiAutoTestCase.objects.create(
        suite=suite,
        name='profile',
        method='GET',
        url='https://example.com/profile',
        headers={'Authorization': 'Bearer {{token}}'},
        expected_status=200,
        sort_order=2,
        created_by=test_user,
    )

    responses = [
        _fake_response({'token': 'T123'}),
        _fake_response({'ok': True}),
    ]

    with patch('qa_center.api_auto_executor.requests.request', side_effect=responses) as request_mock:
        result = run_api_auto_test(suite.id, test_user)

    assert result.status == 'passed'
    assert request_mock.call_count == 2
    second_call = request_mock.call_args_list[1]
    assert second_call.kwargs['headers']['Authorization'] == 'Bearer T123'


@pytest.mark.django_db
def test_single_auto_case_execute_initializes_environment_variables(auth_client, test_project, test_user):
    TestEnvironment.objects.create(
        project=test_project,
        name='default',
        base_url='https://example.com',
        variables={'api_key': 'KEY123'},
        is_default=True,
        created_by=test_user,
    )
    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        name='single suite',
        created_by=test_user,
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        name='ping',
        method='GET',
        url='/ping',
        headers={'X-Api-Key': '{{api_key}}'},
        expected_status=200,
        created_by=test_user,
    )

    with patch('qa_center.api_auto_executor.requests.request', return_value=_fake_response({'ok': True})) as request_mock:
        response = auth_client.post(f'/api/qa/auto-cases/{case.id}/execute/')

    assert response.status_code == 200
    assert request_mock.call_count == 1
    call = request_mock.call_args
    assert call.kwargs['url'] == 'https://example.com/ping'
    assert call.kwargs['headers']['X-Api-Key'] == 'KEY123'
