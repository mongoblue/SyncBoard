import json
import pytest
from io import StringIO
from django.core.management import call_command
from django.contrib.auth.models import User
from room.models import Project
from qa_center.models import ApiTestCase, TestRun, TestRunCaseResult, TestResult


@pytest.fixture
def setup_batch_in_old_format(db):
    user = User.objects.create_user(username='tester', password='pass')
    project = Project.objects.create(name='Test', owner=user)
    case = ApiTestCase.objects.create(
        name='c1', url='/api/x', method='GET', expected_status=200,
        project=project, created_by=user, expected_response={'assertions': []},
    )
    # 模拟老的 TestResult.test_log
    log = {
        'summary': {'total': 3, 'passed': 2, 'failed': 1, 'pass_rate': 66.67},
        'results': [
            {'case_id': case.id, 'case_name': 'c1', 'type': 'api', 'passed': True,
             'response_time_ms': 100, 'message': 'ok',
             'request': {'method': 'GET', 'url': '/api/x', 'headers': {}, 'body': None},
             'response': {'status_code': 200, 'headers': {}, 'body': '{}'},
             'assertions': []},
            {'case_id': case.id, 'case_name': 'c1', 'type': 'api', 'passed': True,
             'response_time_ms': 120, 'message': 'ok',
             'request': {'method': 'GET', 'url': '/api/x', 'headers': {}, 'body': None},
             'response': {'status_code': 200, 'headers': {}, 'body': '{}'},
             'assertions': []},
            {'case_id': case.id, 'case_name': 'c1', 'type': 'api', 'passed': False,
             'response_time_ms': 500, 'message': 'failed',
             'request': {'method': 'GET', 'url': '/api/x', 'headers': {}, 'body': None},
             'response': {'status_code': 500, 'headers': {}, 'body': '{}'},
             'assertions': [{'passed': False, 'error_message': '500'}]},
        ],
    }
    tr = TestResult.objects.create(
        test_type='api', name='old-batch', project=project,
        api_test_case=case, status='failed', executed_by=user,
        duration_ms=720, test_log=json.dumps(log, ensure_ascii=False),
    )
    return tr, project, case


@pytest.mark.django_db
def test_backfill_creates_test_run(setup_batch_in_old_format):
    tr, project, case = setup_batch_in_old_format
    out = StringIO()
    call_command('backfill_test_runs', '--days=90', stdout=out)
    assert TestRun.objects.filter(project=project, name='old-batch').count() == 1
    run = TestRun.objects.get(project=project, name='old-batch')
    assert run.total_count == 3
    assert run.passed_count == 2
    assert run.failed_count == 1
    assert TestRunCaseResult.objects.filter(test_run=run).count() == 3
