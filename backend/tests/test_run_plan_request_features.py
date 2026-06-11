"""TestRunPlan 请求能力（M3.4）端到端测试。

验证：
- query_params 渲染后传给 requests params=
- form_files 转 file tuples 传给 requests files=
- enable_cookie_session=False 时绕开计划 Session
"""
from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from qa_center.models import ApiAutoTestCase, ApiAutoTestSuite, TestRunPlan


@pytest.fixture
def suite(test_project, test_user):
    return ApiAutoTestSuite.objects.create(name='S4', project=test_project, created_by=test_user)


def _resp(status=200, body='{"ok": true}'):
    m = MagicMock()
    m.status_code = status
    m.text = body
    m.headers = {'Content-Type': 'application/json'}
    m.cookies = {}
    try:
        m.json.return_value = json.loads(body)
    except Exception:
        m.json.return_value = {}
    m.elapsed.total_seconds.return_value = 0.01
    return m


@pytest.mark.django_db
class TestRequestFeatures:
    def test_query_params_passed_to_requests(self, test_project, test_user, suite):
        case = ApiAutoTestCase.objects.create(
            name='c1', suite=suite, url='http://x.invalid/search',
            method='GET',
            query_params={'q': '{{kw}}', 'page': 2},
            sort_order=0, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='qp',
            case_ids=[case.id], parallel=False, created_by=test_user,
        )

        captured = {}

        def _record(method, url, **kwargs):
            captured['params'] = kwargs.get('params')
            return _resp()

        from qa_center.run_plan_executor import TestRunPlanExecutor
        # 给 plan 一个简单变量池来渲染 {{kw}}：通过 environment（无）就只剩 base 渲染
        # 这里 case.url 已是绝对地址；{{kw}} 不会被解析，所以把它放到 query 里能看到原样
        # 为模拟环境变量，给 plan 一个 environment_id=None；模板未命中保留原样
        with patch('requests.Session.request', side_effect=_record):
            TestRunPlanExecutor(plan, user=test_user).execute()

        # 未渲染的 {{kw}} 保留原样，方便我们断言到 params 真的被传了
        params = captured['params']
        assert params is not None
        pairs = dict(params) if isinstance(params, list) else dict(params.items())
        # page 是 int -> 字符串 '2'
        assert ('page', '2') in params
        assert ('q', '{{kw}}') in params

    def test_form_files_become_multipart(self, test_project, test_user, suite):
        case = ApiAutoTestCase.objects.create(
            name='upload', suite=suite, url='http://x.invalid/upload',
            method='POST',
            content_type='multipart/form-data',
            form_files=[{
                'name': 'file', 'filename': 'hi.txt',
                'content': 'hello world', 'content_type': 'text/plain',
            }],
            sort_order=0, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='upload',
            case_ids=[case.id], parallel=False, created_by=test_user,
        )

        captured = {}

        def _record(method, url, **kwargs):
            captured['files'] = kwargs.get('files')
            captured['headers'] = dict(kwargs.get('headers') or {})
            return _resp()

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.Session.request', side_effect=_record):
            TestRunPlanExecutor(plan, user=test_user).execute()

        files = captured['files']
        assert files is not None and len(files) == 1
        field, (filename, content_bytes, ctype) = files[0]
        assert field == 'file'
        assert filename == 'hi.txt'
        assert content_bytes == b'hello world'
        assert ctype == 'text/plain'
        # multipart 模式下不应该再硬塞 Content-Type（要让 requests 自己加 boundary）
        assert 'Content-Type' not in captured['headers']
        assert 'content-type' not in captured['headers']

    def test_base64_file_content_decoded(self, test_project, test_user, suite):
        raw = b'\x89PNG\r\n\x1a\n_fake_png_'
        case = ApiAutoTestCase.objects.create(
            name='png', suite=suite, url='http://x.invalid/upload',
            method='POST',
            form_files=[{
                'name': 'avatar', 'filename': 'a.png',
                'content': base64.b64encode(raw).decode('ascii'),
                'encoding': 'base64',
                'content_type': 'image/png',
            }],
            sort_order=0, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='png-up',
            case_ids=[case.id], parallel=False, created_by=test_user,
        )

        captured = {}

        def _record(method, url, **kwargs):
            captured['files'] = kwargs.get('files')
            return _resp()

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.Session.request', side_effect=_record):
            TestRunPlanExecutor(plan, user=test_user).execute()

        assert captured['files'][0][1][1] == raw

    def test_enable_cookie_session_false_uses_module_request(
        self, test_project, test_user, suite,
    ):
        """enable_cookie_session=False 时应走 requests.request 而非 Session.request。"""
        case = ApiAutoTestCase.objects.create(
            name='no-session', suite=suite, url='http://x.invalid/x',
            method='GET',
            enable_cookie_session=False,
            sort_order=0, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='no-sess',
            case_ids=[case.id], parallel=False, created_by=test_user,
        )

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.request', return_value=_resp()) as mod_call, \
             patch('requests.Session.request', return_value=_resp()) as sess_call:
            TestRunPlanExecutor(plan, user=test_user).execute()

        assert mod_call.called, '应走模块级 requests.request'
        assert not sess_call.called, '不应走 Session.request'

    def test_enable_cookie_session_true_uses_session(
        self, test_project, test_user, suite,
    ):
        case = ApiAutoTestCase.objects.create(
            name='with-session', suite=suite, url='http://x.invalid/x',
            method='GET',
            enable_cookie_session=True,
            sort_order=0, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='with-sess',
            case_ids=[case.id], parallel=False, created_by=test_user,
        )

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.request', return_value=_resp()) as mod_call, \
             patch('requests.Session.request', return_value=_resp()) as sess_call:
            TestRunPlanExecutor(plan, user=test_user).execute()

        assert sess_call.called
        assert not mod_call.called

    def test_no_query_params_no_files_kwargs_are_none(
        self, test_project, test_user, suite,
    ):
        """空配置应传 params=None, files=None，不影响普通请求。"""
        case = ApiAutoTestCase.objects.create(
            name='plain', suite=suite, url='http://x.invalid/plain',
            method='GET',
            sort_order=0, created_by=test_user,
        )
        plan = TestRunPlan.objects.create(
            project=test_project, name='plain',
            case_ids=[case.id], parallel=False, created_by=test_user,
        )

        captured = {}

        def _record(method, url, **kwargs):
            captured.update(kwargs)
            return _resp()

        from qa_center.run_plan_executor import TestRunPlanExecutor
        with patch('requests.Session.request', side_effect=_record):
            TestRunPlanExecutor(plan, user=test_user).execute()

        assert captured.get('params') is None
        assert captured.get('files') is None
