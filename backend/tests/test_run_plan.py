"""TestRunPlan 测试 - 模型 / 序列化器校验 / 执行器并发与进度。"""
import json
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth.models import User

from qa_center.models import (
    ApiAutoTestSuite, ApiAutoTestCase, ApiAutoTestResult,
    ApiAutoTestCaseResult, TestRunPlan,
)


# ---------- fixtures ----------

@pytest.fixture
def suite(test_project, test_user):
    return ApiAutoTestSuite.objects.create(
        name='S1', project=test_project, created_by=test_user,
    )


@pytest.fixture
def cases(suite, test_user):
    out = []
    for i in range(3):
        out.append(ApiAutoTestCase.objects.create(
            name=f'case-{i}',
            suite=suite,
            url=f'http://example.invalid/c{i}',
            method='GET',
            expected_status=200,
            sort_order=i,
            timeout_seconds=5,
            created_by=test_user,
        ))
    return out


# ---------- 校验：CRUD + serializer ----------

@pytest.mark.django_db
class TestRunPlanCrud:
    def test_create_requires_auth(self, client, test_project):
        resp = client.post('/api/qa/run-plans/', data={
            'project': test_project.id,
            'name': 'plan-1',
            'case_ids': [],
        }, content_type='application/json')
        assert resp.status_code in (401, 403)

    def test_create_rejects_empty_case_ids(self, auth_client, test_project):
        resp = auth_client.post('/api/qa/run-plans/', data={
            'project': test_project.id,
            'name': 'plan-empty',
            'case_ids': [],
        }, content_type='application/json')
        assert resp.status_code == 400
        assert 'case_ids' in resp.json()

    def test_create_rejects_cases_from_other_project(
        self, auth_client, test_project, test_user, suite, cases,
    ):
        # 用一个不存在的 ID 触发跨项目校验
        resp = auth_client.post('/api/qa/run-plans/', data={
            'project': test_project.id,
            'name': 'plan-cross',
            'case_ids': [cases[0].id, 999999],
        }, content_type='application/json')
        assert resp.status_code == 400
        assert 'case_ids' in resp.json()

    def test_create_normalizes_and_dedupes_case_ids(
        self, auth_client, test_project, cases,
    ):
        resp = auth_client.post('/api/qa/run-plans/', data={
            'project': test_project.id,
            'name': 'plan-dedup',
            'case_ids': [cases[0].id, cases[0].id, cases[1].id],
        }, content_type='application/json')
        assert resp.status_code == 201, resp.content
        plan = TestRunPlan.objects.get(name='plan-dedup')
        assert plan.case_ids == [cases[0].id, cases[1].id]
        assert plan.created_by is not None

    def test_max_workers_bounds(self, auth_client, test_project, cases):
        resp = auth_client.post('/api/qa/run-plans/', data={
            'project': test_project.id,
            'name': 'plan-mw',
            'case_ids': [cases[0].id],
            'max_workers': 999,
        }, content_type='application/json')
        assert resp.status_code == 400

    def test_list_filters_by_project(
        self, auth_client, test_project, test_user, cases,
    ):
        TestRunPlan.objects.create(
            project=test_project, name='A',
            case_ids=[cases[0].id], created_by=test_user,
        )
        resp = auth_client.get(f'/api/qa/run-plans/?project={test_project.id}')
        assert resp.status_code == 200
        names = [p['name'] for p in resp.data['results']]
        assert 'A' in names

    def test_cases_endpoint_lists_active_only(
        self, auth_client, test_project, cases,
    ):
        cases[0].is_active = False
        cases[0].save()
        resp = auth_client.get(f'/api/qa/run-plans/cases/?project={test_project.id}')
        assert resp.status_code == 200
        ids = [c['id'] for c in resp.data['results']]
        assert cases[0].id not in ids
        assert cases[1].id in ids


# ---------- 执行器：串行 / 并发 / 进度 / 中止 ----------

def _mock_response(status_code=200, body='{"ok": true}'):
    m = MagicMock()
    m.status_code = status_code
    m.text = body
    m.headers = {'Content-Type': 'application/json'}
    m.json.return_value = json.loads(body) if body.startswith('{') else {}
    m.elapsed.total_seconds.return_value = 0.01
    return m


@pytest.mark.django_db
class TestRunPlanExecutor:
    def _make_plan(self, project, user, case_ids, **kwargs):
        return TestRunPlan.objects.create(
            project=project, name='exec', case_ids=case_ids,
            created_by=user, **kwargs,
        )

    def test_serial_all_pass(self, test_project, test_user, cases):
        from qa_center.run_plan_executor import TestRunPlanExecutor
        plan = self._make_plan(test_project, test_user, [c.id for c in cases])
        with patch('requests.Session.request', return_value=_mock_response()):
            result = TestRunPlanExecutor(plan, user=test_user).execute()
        assert result.status == 'passed'
        assert result.total_cases == 3
        assert result.passed_cases == 3
        assert result.failed_cases == 0
        assert ApiAutoTestCaseResult.objects.filter(test_result=result).count() == 3

    def test_serial_records_failure(self, test_project, test_user, cases):
        from qa_center.run_plan_executor import TestRunPlanExecutor
        plan = self._make_plan(test_project, test_user, [c.id for c in cases])
        # 第一条返回 500
        responses = [_mock_response(500, '{"err":1}')] + [_mock_response()] * 2
        with patch('requests.Session.request', side_effect=responses):
            result = TestRunPlanExecutor(plan, user=test_user).execute()
        assert result.status == 'failed'
        assert result.passed_cases == 2
        assert result.failed_cases == 1

    def test_stop_on_failure_serial(self, test_project, test_user, cases):
        from qa_center.run_plan_executor import TestRunPlanExecutor
        plan = self._make_plan(
            test_project, test_user, [c.id for c in cases],
            stop_on_failure=True,
        )
        responses = [_mock_response(500)] + [_mock_response()] * 2
        with patch('requests.Session.request', side_effect=responses):
            result = TestRunPlanExecutor(plan, user=test_user).execute()
        # 应该只跑了第一条
        assert ApiAutoTestCaseResult.objects.filter(test_result=result).count() == 1
        assert result.error_message == '遇到失败已中止后续用例'

    def test_parallel_all_executed(self, test_project, test_user, cases):
        from qa_center.run_plan_executor import TestRunPlanExecutor
        plan = self._make_plan(
            test_project, test_user, [c.id for c in cases],
            parallel=True, max_workers=3,
        )
        with patch('requests.Session.request', return_value=_mock_response()):
            result = TestRunPlanExecutor(plan, user=test_user).execute()
        assert result.passed_cases == 3
        assert ApiAutoTestCaseResult.objects.filter(test_result=result).count() == 3

    def test_progress_broadcast_called(self, test_project, test_user, cases):
        from qa_center.run_plan_executor import TestRunPlanExecutor
        plan = self._make_plan(test_project, test_user, [c.id for c in cases])
        with patch('qa_center.run_plan_executor._broadcast') as bc, \
             patch('requests.Session.request', return_value=_mock_response()):
            TestRunPlanExecutor(plan, user=test_user).execute()
        events = [call.args[0] for call in bc.call_args_list]
        phases = [e['phase'] for e in events]
        assert phases.count('started') == 1
        assert phases.count('case_done') == 3
        assert phases.count('finished') == 1
        # case_done 事件必须带上前端进度条所需字段
        case_done_events = [e for e in events if e['phase'] == 'case_done']
        for e in case_done_events:
            assert 'case_passed' in e and isinstance(e['case_passed'], bool)
            assert 'case_error' in e
            assert 'completed' in e and 'total' in e
            assert e['type'] == 'run_plan_progress'

    def test_timeout_marks_error(self, test_project, test_user, cases):
        import requests as _rq
        from qa_center.run_plan_executor import TestRunPlanExecutor
        plan = self._make_plan(test_project, test_user, [cases[0].id])
        with patch('requests.Session.request', side_effect=_rq.exceptions.Timeout()):
            result = TestRunPlanExecutor(plan, user=test_user).execute()
        assert result.error_cases == 1
        case_result = ApiAutoTestCaseResult.objects.get(test_result=result)
        assert 'timeout' in case_result.error_message.lower()

    def test_case_order_preserved(self, test_project, test_user, cases):
        from qa_center.run_plan_executor import TestRunPlanExecutor
        # 故意打乱顺序传入
        plan = self._make_plan(
            test_project, test_user,
            [cases[2].id, cases[0].id, cases[1].id],
        )
        with patch('requests.Session.request', return_value=_mock_response()):
            result = TestRunPlanExecutor(plan, user=test_user).execute()
        executed = list(
            ApiAutoTestCaseResult.objects
            .filter(test_result=result)
            .order_by('executed_at')
            .values_list('case_id', flat=True)
        )
        assert executed == [cases[2].id, cases[0].id, cases[1].id]


# ---------- 用例结果分页接口 ----------

@pytest.mark.django_db
class TestAutoResultCasesEndpoint:
    def _make_result_with_cases(self, suite, cases, mix=True):
        result = ApiAutoTestResult.objects.create(
            suite=suite, name='r1', status='failed',
            total_cases=len(cases), passed_cases=2, failed_cases=1,
        )
        ApiAutoTestCaseResult.objects.create(
            test_result=result, case=cases[0],
            status_code=200, response_body='ok', response_time_ms=10,
            passed=True, assertion_details=[{'passed': True}],
        )
        ApiAutoTestCaseResult.objects.create(
            test_result=result, case=cases[1],
            status_code=500, response_body='err', response_time_ms=200,
            passed=False, assertion_details=[
                {'passed': False, 'error_message': 'status mismatch'},
            ],
            error_message='',
        )
        ApiAutoTestCaseResult.objects.create(
            test_result=result, case=cases[2],
            status_code=200, response_body='ok2', response_time_ms=50,
            passed=True, assertion_details=[],
        )
        return result

    def test_cases_paginated(self, auth_client, suite, cases):
        result = self._make_result_with_cases(suite, cases)
        resp = auth_client.get(f'/api/qa/auto-results/{result.id}/cases/?page_size=2')
        assert resp.status_code == 200
        assert resp.data['count'] == 3
        assert len(resp.data['results']) == 2
        # brief 不应包含 response_body
        assert 'response_body' not in resp.data['results'][0]

    def test_cases_filter_failed(self, auth_client, suite, cases):
        result = self._make_result_with_cases(suite, cases)
        resp = auth_client.get(f'/api/qa/auto-results/{result.id}/cases/?passed=false')
        assert resp.status_code == 200
        assert resp.data['count'] == 1
        assert resp.data['results'][0]['passed'] is False
        assert 'status mismatch' in resp.data['results'][0]['error_summary']

    def test_cases_order_by_response_time(self, auth_client, suite, cases):
        result = self._make_result_with_cases(suite, cases)
        resp = auth_client.get(
            f'/api/qa/auto-results/{result.id}/cases/?ordering=-response_time_ms'
        )
        times = [r['response_time_ms'] for r in resp.data['results']]
        assert times == sorted(times, reverse=True)

    def test_case_detail_returns_full_body(self, auth_client, suite, cases):
        result = self._make_result_with_cases(suite, cases)
        cr = ApiAutoTestCaseResult.objects.filter(test_result=result).first()
        resp = auth_client.get(
            f'/api/qa/auto-results/{result.id}/case_detail/?case_result_id={cr.id}'
        )
        assert resp.status_code == 200
        assert 'response_body' in resp.data
        assert resp.data['response_body'] == cr.response_body

    def test_case_detail_rejects_foreign_id(self, auth_client, suite, cases, test_user):
        result = self._make_result_with_cases(suite, cases)
        # 另起一个 result
        other = ApiAutoTestResult.objects.create(
            suite=suite, name='r2', status='passed', total_cases=1, passed_cases=1,
        )
        other_cr = ApiAutoTestCaseResult.objects.create(
            test_result=other, case=cases[0], status_code=200,
            response_body='', response_time_ms=1, passed=True, assertion_details=[],
        )
        resp = auth_client.get(
            f'/api/qa/auto-results/{result.id}/case_detail/?case_result_id={other_cr.id}'
        )
        assert resp.status_code == 404
