"""TestEnvironment + TestGlobalVar CRUD 测试 —— M3.2。

需要数据库。涵盖：
- 必填校验 / 同项目重名校验
- is_default 互斥（同项目至多一条 default）
- set_default action
- 全局变量 key 命名规则与脱敏 value_display
"""
from __future__ import annotations

import pytest

from qa_center.models import TestEnvironment, TestGlobalVar


# ---------- TestEnvironment ----------


@pytest.mark.django_db
class TestEnvironmentCrud:
    def test_create_requires_auth(self, client, test_project):
        resp = client.post('/api/qa/environments/', data={
            'project': test_project.id,
            'name': 'dev',
        }, content_type='application/json')
        assert resp.status_code in (401, 403)

    def test_create_first_env_auto_default(self, auth_client, test_project):
        resp = auth_client.post('/api/qa/environments/', data={
            'project': test_project.id,
            'name': 'dev',
            'base_url': 'https://dev.example.com',
            'variables': {'token': 'tok-dev'},
        }, content_type='application/json')
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body['name'] == 'dev'
        # 第一条自动成为默认
        env = TestEnvironment.objects.get(id=body['id'])
        assert env.is_default is True

    def test_second_env_not_default_unless_requested(self, auth_client, test_project):
        TestEnvironment.objects.create(
            project=test_project, name='dev', is_default=True,
        )
        resp = auth_client.post('/api/qa/environments/', data={
            'project': test_project.id,
            'name': 'staging',
        }, content_type='application/json')
        assert resp.status_code == 201
        env2 = TestEnvironment.objects.get(name='staging', project=test_project)
        assert env2.is_default is False

    def test_setting_is_default_demotes_others(self, auth_client, test_project):
        e1 = TestEnvironment.objects.create(project=test_project, name='dev', is_default=True)
        resp = auth_client.post('/api/qa/environments/', data={
            'project': test_project.id,
            'name': 'staging',
            'is_default': True,
        }, content_type='application/json')
        assert resp.status_code == 201
        e1.refresh_from_db()
        assert e1.is_default is False
        e2 = TestEnvironment.objects.get(name='staging', project=test_project)
        assert e2.is_default is True

    def test_duplicate_name_rejected(self, auth_client, test_project):
        TestEnvironment.objects.create(project=test_project, name='dev')
        resp = auth_client.post('/api/qa/environments/', data={
            'project': test_project.id,
            'name': 'dev',
        }, content_type='application/json')
        assert resp.status_code == 400
        assert 'name' in resp.json()

    def test_variables_must_be_dict(self, auth_client, test_project):
        resp = auth_client.post('/api/qa/environments/', data={
            'project': test_project.id,
            'name': 'dev',
            'variables': ['not', 'a', 'dict'],
        }, content_type='application/json')
        assert resp.status_code == 400

    def test_set_default_action(self, auth_client, test_project):
        e1 = TestEnvironment.objects.create(project=test_project, name='dev', is_default=True)
        e2 = TestEnvironment.objects.create(project=test_project, name='staging', is_default=False)
        resp = auth_client.post(f'/api/qa/environments/{e2.id}/set_default/')
        assert resp.status_code == 200
        e1.refresh_from_db()
        e2.refresh_from_db()
        assert e1.is_default is False
        assert e2.is_default is True

    def test_list_filters_by_project(self, auth_client, test_project, test_user):
        from room.models import Project
        other = Project.objects.create(name='Other', owner=test_user)
        TestEnvironment.objects.create(project=test_project, name='dev')
        TestEnvironment.objects.create(project=other, name='dev')
        resp = auth_client.get(f'/api/qa/environments/?project={test_project.id}')
        assert resp.status_code == 200
        items = resp.json().get('results', resp.json())
        names = [e['name'] for e in items]
        assert names == ['dev']  # 只看到本项目


# ---------- TestGlobalVar ----------


@pytest.mark.django_db
class TestGlobalVarCrud:
    def test_create_basic(self, auth_client, test_project):
        resp = auth_client.post('/api/qa/global-vars/', data={
            'project': test_project.id,
            'key': 'admin_user',
            'value': 'admin',
            'description': '默认管理员',
        }, content_type='application/json')
        assert resp.status_code == 201
        gv = TestGlobalVar.objects.get(project=test_project, key='admin_user')
        assert gv.value == 'admin'

    def test_invalid_key(self, auth_client, test_project):
        for bad in ['', '1abc', 'has space', 'with-dash']:
            resp = auth_client.post('/api/qa/global-vars/', data={
                'project': test_project.id,
                'key': bad,
                'value': 'x',
            }, content_type='application/json')
            assert resp.status_code == 400, f'expected 400 for key={bad!r}'

    def test_duplicate_key_rejected(self, auth_client, test_project):
        TestGlobalVar.objects.create(project=test_project, key='token', value='a')
        resp = auth_client.post('/api/qa/global-vars/', data={
            'project': test_project.id,
            'key': 'token',
            'value': 'b',
        }, content_type='application/json')
        assert resp.status_code == 400

    def test_secret_value_masked_in_display(self, auth_client, test_project):
        gv = TestGlobalVar.objects.create(
            project=test_project, key='secret_key',
            value='super-secret-token', is_secret=True,
        )
        resp = auth_client.get(f'/api/qa/global-vars/{gv.id}/')
        assert resp.status_code == 200
        body = resp.json()
        # value 字段仍可读（创建者需要），value_display 是掩码
        assert body['value'] == 'super-secret-token'
        assert body['value_display'] == '*' * 8

    def test_non_secret_value_display_passthrough(self, auth_client, test_project):
        gv = TestGlobalVar.objects.create(
            project=test_project, key='public_key', value='visible',
        )
        resp = auth_client.get(f'/api/qa/global-vars/{gv.id}/')
        assert resp.json()['value_display'] == 'visible'


# ---------- 集成：run-plans 接受 environment 字段 ----------


@pytest.mark.django_db
class TestRunPlanEnvironmentField:
    def test_create_run_plan_with_environment(self, auth_client, test_project, test_user):
        from qa_center.models import ApiAutoTestSuite, ApiAutoTestCase
        suite = ApiAutoTestSuite.objects.create(name='S', project=test_project, created_by=test_user)
        case = ApiAutoTestCase.objects.create(
            name='c1', suite=suite, url='/foo', method='GET', sort_order=0,
            created_by=test_user,
        )
        env = TestEnvironment.objects.create(
            project=test_project, name='dev', base_url='https://x.com',
        )
        resp = auth_client.post('/api/qa/run-plans/', data={
            'project': test_project.id,
            'name': 'plan-with-env',
            'case_ids': [case.id],
            'environment': env.id,
        }, content_type='application/json')
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body['environment'] == env.id
        assert body['environment_name'] == 'dev'
