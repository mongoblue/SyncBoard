"""UI 测试模块生产级加固回归测试。"""
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from qa_center.models import (
    TestEnvironment as EnvModel,
    TestGlobalVar as GlobalVarModel,
    TestResult as ResultModel,
    UiTestCase,
)
from qa_center.ui_execution import (
    UI_STEP_ACTIONS,
    prepare_ui_case_payload,
    render_ui_case_data,
    validate_ui_steps,
)
from qa_center.workers import runner_supervisor
from qa_center.workers.runner_worker import _classify_error, _to_int


@pytest.mark.django_db
class TestUiStepsValidation:
    def test_valid_actions_pass(self):
        assert validate_ui_steps([
            {'action': 'click', 'selector': '#a'},
            {'action': 'drag_and_drop', 'selector': '#a', 'value': '#b'},
            {'action': 'right_click', 'selector': '#a'},
        ]) == []

    def test_unknown_action_rejected(self):
        errs = validate_ui_steps([{'action': 'fly_to_moon'}])
        assert errs
        assert '不支持' in errs[0]

    def test_whitelist_includes_frontend_actions(self):
        for action in [
            'right_click', 'upload', 'keydown', 'iframe_switch',
            'alert_handle', 'assert_exists', 'drag_and_drop',
        ]:
            assert action in UI_STEP_ACTIONS


class TestRunnerWorkerHelpers:
    def test_to_int_safe(self):
        assert _to_int('12.5') == 12
        assert _to_int('abc', 7) == 7
        assert _to_int(None, 3) == 3

    def test_classify_unsupported(self):
        assert _classify_error(ValueError('UNSUPPORTED_ACTION:foo')) == 'UNSUPPORTED_ACTION'


@pytest.mark.django_db
class TestUiVariableRendering:
    def test_render_base_url_and_vars(self, test_project, test_user):
        env = EnvModel.objects.create(
            project=test_project,
            name='staging',
            base_url='https://app.example.com',
            variables={'user': 'alice'},
            is_default=True,
            created_by=test_user,
        )
        GlobalVarModel.objects.create(
            project=test_project, key='token', value='secret', is_secret=True, created_by=test_user
        )
        case = UiTestCase.objects.create(
            project=test_project,
            name='login',
            url='{{base_url}}/login',
            steps=[{'action': 'fill', 'selector': '#u', 'value': '{{user}}'}],
            environment=env,
            created_by=test_user,
        )
        case_data, meta = prepare_ui_case_payload(
            test_project,
            url=case.url,
            steps=case.steps,
            case=case,
        )
        assert case_data['url'] == 'https://app.example.com/login'
        assert case_data['steps'][0]['value'] == 'alice'
        assert meta['environment_name'] == 'staging'
        assert meta['variables_preview']['token'] == '***'
        assert meta['unresolved_variables'] == []

    def test_request_override_environment(self, test_project, test_user):
        default_env = EnvModel.objects.create(
            project=test_project, name='default', base_url='https://default.example',
            is_default=True, created_by=test_user,
        )
        other = EnvModel.objects.create(
            project=test_project, name='other', base_url='https://other.example',
            is_default=False, created_by=test_user,
        )
        case = UiTestCase.objects.create(
            project=test_project, name='c', url='{{base_url}}/x', steps=[],
            environment=default_env, created_by=test_user,
        )
        case_data, meta = prepare_ui_case_payload(
            test_project, url=case.url, steps=[], case=case, environment_id=other.id
        )
        assert case_data['url'] == 'https://other.example/x'
        assert meta['environment_id'] == other.id

    def test_unresolved_kept(self, test_project):
        url, steps, unresolved = render_ui_case_data(
            '{{missing}}/path',
            [{'action': 'fill', 'selector': '#a', 'value': '{{nope}}'}],
            {},
        )
        assert url == '{{missing}}/path'
        assert steps[0]['value'] == '{{nope}}'
        assert 'missing' in unresolved
        assert 'nope' in unresolved


@pytest.mark.django_db
class TestUiSupervisorEvents:
    def test_record_and_peek_events(self):
        tid = 'abc123task'
        runner_supervisor.record_event(tid, {'type': 'step_start', 'index': 0})
        runner_supervisor.record_event(tid, {'type': 'finished', 'success': True})
        peeks = runner_supervisor.peek_events(tid)
        assert len(peeks) == 2
        assert '_ts' in peeks[0]
        # peek should not consume
        assert len(runner_supervisor.peek_events(tid)) == 2
        got = runner_supervisor.get_events(tid)
        assert len(got) == 2
        assert runner_supervisor.peek_events(tid) == []

    def test_abort_marks_flag(self):
        tid = 'abort-task-1'
        runner_supervisor.clear_aborted(tid)
        # no process, abort returns False but mark still? only marks if proc exists
        assert runner_supervisor.abort_runner(tid) is False
        # simulate register dummy process-like object
        class Dummy:
            def poll(self):
                return 0
            def terminate(self):
                return None
        runner_supervisor.register_runner(tid, Dummy())
        assert runner_supervisor.abort_runner(tid) is True
        assert runner_supervisor.is_aborted(tid) is True
        runner_supervisor.unregister_runner(tid)
        runner_supervisor.clear_aborted(tid)


@pytest.mark.django_db
class TestUiApiContracts:
    def test_create_case_with_environment(self, auth_client, test_project, test_user):
        env = EnvModel.objects.create(
            project=test_project, name='e1', base_url='https://e1.test', created_by=test_user
        )
        resp = auth_client.post('/api/qa/ui-cases/', {
            'project': test_project.id,
            'name': 'ui-1',
            'url': '{{base_url}}/home',
            'environment': env.id,
            'steps': [{'action': 'click', 'selector': '#ok'}],
        }, content_type='application/json')
        assert resp.status_code in (200, 201), resp.content
        case = UiTestCase.objects.get(name='ui-1')
        assert case.environment_id == env.id

    def test_reject_unknown_step_action(self, auth_client, test_project):
        resp = auth_client.post('/api/qa/ui-cases/', {
            'project': test_project.id,
            'name': 'bad',
            'url': 'https://example.com',
            'steps': [{'action': 'teleport'}],
        }, content_type='application/json')
        assert resp.status_code == 400

    def test_run_sync_payload_shape(self, auth_client, test_project, test_user):
        case = UiTestCase.objects.create(
            project=test_project,
            name='sync-run',
            url='https://example.com',
            steps=[{'action': 'wait', 'value': '10'}],
            created_by=test_user,
        )

        def fake_execute(case_data, on_event, timeout_seconds=300, task_id=None):
            tid = task_id or 'task-sync-1'
            on_event({'type': 'supervisor_meta', 'task_id': tid, 'worker_pid': 1})
            on_event({'type': 'started', 'temp_dir': ''})
            on_event({'type': 'step_log', 'message': 'ok'})
            on_event({'type': 'finished', 'success': True, 'summary': {'passed': 1, 'failed': 0, 'total': 1}, 'task_id': tid})
            return {'type': 'finished', 'success': True, 'summary': {'passed': 1, 'failed': 0, 'total': 1}, 'task_id': tid}

        # prepare_and_execute_ui_case 内部 from .workers.runner_supervisor import execute_ui_case
        with patch('qa_center.workers.runner_supervisor.execute_ui_case', side_effect=fake_execute), \
             patch('qa_center.result_sink.sync_ui_run_from_test_result', return_value=None):
            resp = auth_client.post(f'/api/qa/ui-cases/{case.id}/run/', {}, content_type='application/json')
        assert resp.status_code == 200, resp.content
        payload = resp.data
        assert 'success' in payload
        assert 'logs' in payload
        assert 'step_screenshots' in payload
        assert 'summary' in payload
        assert payload.get('success') is True

    def test_run_async_returns_task_id(self, auth_client, test_project, test_user):
        case = UiTestCase.objects.create(
            project=test_project,
            name='async-run',
            url='https://example.com',
            steps=[{'action': 'wait', 'value': '10'}],
            created_by=test_user,
        )

        def fake_execute(case_data, on_event, timeout_seconds=300, task_id=None):
            tid = task_id or 'task-async-1'
            on_event({'type': 'supervisor_meta', 'task_id': tid, 'worker_pid': 2})
            on_event({'type': 'finished', 'success': True, 'summary': {'passed': 1, 'failed': 0, 'total': 1}, 'task_id': tid})
            return {'type': 'finished', 'success': True, 'summary': {'passed': 1, 'failed': 0, 'total': 1}, 'task_id': tid, 'aborted': False}

        with patch('qa_center.workers.runner_supervisor.execute_ui_case', side_effect=fake_execute), \
             patch('qa_center.result_sink.sync_ui_run_from_test_result', return_value=None), \
             patch('threading.Thread') as th:
            # run worker inline
            def run_inline(target=None, name=None, daemon=None):
                class T:
                    def start(self_inner):
                        if target:
                            target()
                return T()
            th.side_effect = run_inline
            resp = auth_client.post(f'/api/qa/ui-cases/{case.id}/run_async/', {}, content_type='application/json')
        assert resp.status_code == 202, resp.content
        assert resp.data['task_id']
        assert resp.data['result_id']
        tr = ResultModel.objects.get(id=resp.data['result_id'])
        assert tr.task_id == resp.data['task_id']

    def test_path_guard_rejects_traversal(self, auth_client, test_project, test_user):
        tr = ResultModel.objects.create(
            test_type='ui',
            name='shot',
            project=test_project,
            executed_by=test_user,
            status='passed',
            task_id='shot-task-1',
            temp_dir_path='C:/not-under-root',
            started_at=timezone.now(),
        )
        resp = auth_client.get('/api/qa/ui-run/screenshot/', {
            'task_id': 'shot-task-1',
            'path': '../secrets.txt',
        })
        assert resp.status_code in (400, 404)


@pytest.mark.django_db
class TestExecuteUiTestCasesBatch:
    def test_batch_structure_preserved(self, test_project, test_user):
        from qa_center.views_ui_test import execute_ui_test_cases

        case = UiTestCase.objects.create(
            project=test_project,
            name='batch-ui',
            url='https://example.com',
            steps=[{'action': 'wait', 'value': '1'}],
            created_by=test_user,
        )

        def fake_execute(case_data, on_event, timeout_seconds=300, task_id=None):
            tid = task_id or 'batch-1'
            on_event({'type': 'finished', 'success': True, 'summary': {'passed': 1, 'failed': 0, 'total': 1}, 'task_id': tid})
            return {'type': 'finished', 'success': True, 'summary': {'passed': 1, 'failed': 0, 'total': 1}, 'task_id': tid}

        with patch('qa_center.workers.runner_supervisor.execute_ui_case', side_effect=fake_execute), \
             patch('qa_center.result_sink.sync_ui_run_from_test_result', return_value=None):
            results = execute_ui_test_cases([case.id])
        assert len(results) == 1
        item = results[0]
        assert item['case_id'] == case.id
        assert item['type'] == 'ui'
        assert 'request' in item and 'response' in item and 'steps' in item
        assert item['passed'] is True