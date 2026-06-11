"""TestRunPlan Extractor 端到端测试 —— M3.3。

验证：
- 串行执行下，前一条用例 extractor 抽到的变量会注入后一条用例的 URL/headers/body
- 并行执行下，抽取仍执行但不在 case 间传递（日志警告）
- extractor 失败用 default_value 回填
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from qa_center.models import (
    ApiAutoTestCase, ApiAutoTestSuite, ApiAutoTestExtractor, TestRunPlan,
)


@pytest.fixture
def suite(test_project, test_user):
    return ApiAutoTestSuite.objects.create(name='S', project=test_project, created_by=test_user)


def _resp(status=200, body='{"token": "T123", "user": {"id": 9}}', headers=None, cookies=None):
    m = MagicMock()
    m.status_code = status
    m.text = body
    m.headers = headers or {'Content-Type': 'application/json'}
    m.cookies = cookies or {}
    try:
        m.json.return_value = json.loads(body)
    except Exception:
        m.json.return_value = {}
    m.elapsed.total_seconds.return_value = 0.01
    return m


@pytest.mark.django_db
class TestExtractorPropagation:
    def test_serial_passes_extracted_var_to_next_case(self, test_project, test_user, suite):
        # case A: 登录拿 token -> case B: 用 {{token}} 调下一个接口
        login = ApiAutoTestCase.objects.create(
            name='login', suite=suite, url='http://x.invalid/login',
            method='POST', sort_order=0, created_by=test_user,
        )
        ApiAutoTestExtractor.objects.create(
            case=login, name='token', source='body', expression='token',
        )
        get_user = ApiAutoTestCase.objects.create(
            name='get_user', suite=suite, url='http://x.invalid/users/me',
            method='GET',
            headers={'Authorization': 'Bearer {{token}}'},
            sort_order=1, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='chain',
            case_ids=[login.id, get_user.id], parallel=False,
            created_by=test_user,
        )

        sent_headers = []

        def _record_request(method, url, **kwargs):
            sent_headers.append(dict(kwargs.get('headers') or {}))
            return _resp(body='{"token": "T123"}' if 'login' in url else '{"ok": true}')

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.Session.request', side_effect=_record_request):
            result = TestRunPlanExecutor(plan, user=test_user).execute()

        assert result.status == 'passed'
        assert len(sent_headers) == 2
        # 第二条请求的 Authorization 头里应当出现 T123（来自第一条抽取）
        assert sent_headers[1].get('Authorization') == 'Bearer T123'

    def test_url_substitution_with_extracted_var(self, test_project, test_user, suite):
        create = ApiAutoTestCase.objects.create(
            name='create', suite=suite, url='http://x.invalid/items',
            method='POST', sort_order=0, created_by=test_user,
        )
        ApiAutoTestExtractor.objects.create(
            case=create, name='item_id', source='body', expression='user.id',
        )
        fetch = ApiAutoTestCase.objects.create(
            name='fetch', suite=suite, url='http://x.invalid/items/{{item_id}}',
            method='GET', sort_order=1, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='chain-url',
            case_ids=[create.id, fetch.id], parallel=False,
            created_by=test_user,
        )

        called_urls = []

        def _record(method, url, **kwargs):
            called_urls.append(url)
            return _resp()

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.Session.request', side_effect=_record):
            TestRunPlanExecutor(plan, user=test_user).execute()

        assert called_urls[0] == 'http://x.invalid/items'
        assert called_urls[1] == 'http://x.invalid/items/9'  # user.id=9 from body

    def test_default_value_used_when_extract_misses(self, test_project, test_user, suite):
        first = ApiAutoTestCase.objects.create(
            name='first', suite=suite, url='http://x.invalid/a',
            method='GET', sort_order=0, created_by=test_user,
        )
        ApiAutoTestExtractor.objects.create(
            case=first, name='fallback_id', source='body',
            expression='nonexistent.path', default_value='ANON',
        )
        second = ApiAutoTestCase.objects.create(
            name='second', suite=suite, url='http://x.invalid/users/{{fallback_id}}',
            method='GET', sort_order=1, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='chain-default',
            case_ids=[first.id, second.id], parallel=False,
            created_by=test_user,
        )

        urls = []

        def _record(method, url, **kwargs):
            urls.append(url)
            return _resp(body='{"different": "shape"}')

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.Session.request', side_effect=_record):
            TestRunPlanExecutor(plan, user=test_user).execute()

        assert urls[1] == 'http://x.invalid/users/ANON'

    def test_parallel_extractions_do_not_propagate(self, test_project, test_user, suite):
        # 在并行模式下，extractor 仍执行但不影响其他 case 的渲染
        a = ApiAutoTestCase.objects.create(
            name='A', suite=suite, url='http://x.invalid/a',
            method='GET', sort_order=0, created_by=test_user,
        )
        ApiAutoTestExtractor.objects.create(
            case=a, name='shared', source='body', expression='token',
        )
        b = ApiAutoTestCase.objects.create(
            name='B', suite=suite, url='http://x.invalid/b',
            method='GET',
            # 即使写了 {{shared}}，并发下也不会被替换，应保持原样
            headers={'X-Shared': '{{shared}}'},
            sort_order=1, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='parallel',
            case_ids=[a.id, b.id], parallel=True, max_workers=2,
            created_by=test_user,
        )

        seen = []

        def _record(method, url, **kwargs):
            seen.append({'url': url, 'headers': dict(kwargs.get('headers') or {})})
            return _resp(body='{"token": "PARALLEL_TOK"}')

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.Session.request', side_effect=_record):
            TestRunPlanExecutor(plan, user=test_user).execute()

        # 找出 B 那次调用：其 X-Shared 应当仍是 {{shared}} 原样（并发下不传递）
        b_call = next(s for s in seen if s['url'].endswith('/b'))
        assert b_call['headers'].get('X-Shared') == '{{shared}}'

    def test_extracted_payload_appears_in_progress_event(self, test_project, test_user, suite):
        case = ApiAutoTestCase.objects.create(
            name='single', suite=suite, url='http://x.invalid/x',
            method='GET', sort_order=0, created_by=test_user,
        )
        ApiAutoTestExtractor.objects.create(
            case=case, name='tok', source='body', expression='token',
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='progress',
            case_ids=[case.id], parallel=False,
            created_by=test_user,
        )

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('qa_center.run_plan_executor._broadcast') as bc, \
             patch('requests.Session.request', return_value=_resp()):
            TestRunPlanExecutor(plan, user=test_user).execute()

        events = [call.args[0] for call in bc.call_args_list]
        case_done = [e for e in events if e.get('phase') == 'case_done']
        assert case_done, 'expected at least one case_done event'
        assert 'extracted' in case_done[0]
        names = [item['name'] for item in case_done[0]['extracted']]
        assert 'tok' in names
