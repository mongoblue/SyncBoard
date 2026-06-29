"""Bug 跟踪模块测试 - 状态机、API、生命周期"""
import pytest
from django.contrib.auth.models import User

from bug_tracker.models import Bug, BugComment, BugTransition
from bug_tracker.state_machine import (
    BUG_TRANSITIONS,
    TransitionError,
    allowed_next_statuses,
    can_transition,
    validate_transition,
)


# ============== 状态机单测 ==============

class TestStateMachine:
    def test_legal_transition_new_to_confirmed(self):
        assert can_transition('new', 'confirmed') is True

    def test_legal_transition_fixed_to_verifying(self):
        assert can_transition('fixed', 'verifying') is True

    def test_illegal_transition_new_to_fixed(self):
        assert can_transition('new', 'fixed') is False

    def test_illegal_transition_closed_to_fixing(self):
        assert can_transition('closed', 'fixing') is False

    def test_self_transition_rejected(self):
        with pytest.raises(TransitionError):
            validate_transition('new', 'new')

    def test_validate_raises_on_illegal(self):
        with pytest.raises(TransitionError) as exc:
            validate_transition('new', 'closed')
        assert 'new' in str(exc.value) and 'closed' in str(exc.value)

    def test_allowed_next_for_new(self):
        nexts = allowed_next_statuses('new')
        assert set(nexts) == {'confirmed', 'rejected', 'assigned'}

    def test_terminal_states_can_reopen(self):
        assert can_transition('closed', 'reopened') is True
        assert can_transition('rejected', 'reopened') is True

    def test_full_lifecycle_legal_chain(self):
        chain = ['new', 'confirmed', 'assigned', 'fixing', 'fixed', 'verifying', 'closed']
        for a, b in zip(chain, chain[1:]):
            validate_transition(a, b)  # must not raise


# ============== API 测试 ==============

@pytest.mark.django_db
class TestBugAuth:
    def test_list_requires_auth(self, client):
        resp = client.get('/api/bugs/')
        assert resp.status_code == 403


@pytest.mark.django_db
class TestBugCRUD:
    def test_create_bug(self, auth_client, test_project):
        resp = auth_client.post(
            '/api/bugs/',
            data={
                'project': str(test_project.id),
                'title': '登录按钮无响应',
                'description': '点击没反应',
                'severity': 'major',
                'priority': 'p1',
                'steps_to_reproduce': '1. 打开 /login\n2. 输入用户名密码\n3. 点登录',
                'expected': '跳转首页',
                'actual': '什么都没发生',
            },
            content_type='application/json',
        )
        assert resp.status_code == 201
        bug = Bug.objects.get(title='登录按钮无响应')
        assert bug.status == 'new'
        assert bug.reporter is not None
        # 应自动写一条创建流转
        assert bug.transitions.filter(to_status='new').exists()

    def test_list_filter_by_status(self, auth_client, test_project, test_user):
        Bug.objects.create(project=test_project, title='B1', status='new', reporter=test_user)
        Bug.objects.create(project=test_project, title='B2', status='closed', reporter=test_user)
        resp = auth_client.get(f'/api/bugs/?project={test_project.id}&status=new')
        assert resp.status_code == 200
        titles = [b['title'] for b in resp.data['results']]
        assert 'B1' in titles and 'B2' not in titles

    def test_list_returns_linked_task_field(self, auth_client, test_project, test_user):
        from room.models import Task, Column
        col = Column.objects.filter(project=test_project).first()
        task = Task.objects.create(column=col, title='联动任务')
        Bug.objects.create(
            project=test_project, title='B1', status='new',
            reporter=test_user, linked_task=task,
        )
        resp = auth_client.get(f'/api/bugs/?project={test_project.id}')
        assert resp.status_code == 200
        assert 'linked_task' in resp.data['results'][0]
        assert resp.data['results'][0]['linked_task'] == str(task.id)

    def test_list_returns_allowed_transitions(self, auth_client, test_project, test_user):
        Bug.objects.create(project=test_project, title='B1', status='new', reporter=test_user)

        resp = auth_client.get(f'/api/bugs/?project={test_project.id}')

        assert resp.status_code == 200
        assert set(resp.data['results'][0]['allowed_transitions']) == {'confirmed', 'rejected', 'assigned'}

    def test_update_does_not_change_status(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(
            project=test_project, title='X', status='new', reporter=test_user
        )
        resp = auth_client.patch(
            f'/api/bugs/{bug.id}/',
            data={'title': 'X2', 'severity': 'blocker'},
            content_type='application/json',
        )
        assert resp.status_code == 200
        bug.refresh_from_db()
        assert bug.title == 'X2' and bug.severity == 'blocker'
        assert bug.status == 'new'  # 没改


@pytest.mark.django_db
class TestBugTransition:
    def test_transition_new_to_confirmed(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(project=test_project, title='X', reporter=test_user)
        resp = auth_client.post(
            f'/api/bugs/{bug.id}/transition/',
            data={'to_status': 'confirmed', 'comment': '复现成功'},
            content_type='application/json',
        )
        assert resp.status_code == 200
        bug.refresh_from_db()
        assert bug.status == 'confirmed'
        t = bug.transitions.filter(from_status='new', to_status='confirmed').first()
        assert t is not None and t.comment == '复现成功'

    def test_illegal_transition_rejected_by_api(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(project=test_project, title='X', reporter=test_user)
        resp = auth_client.post(
            f'/api/bugs/{bug.id}/transition/',
            data={'to_status': 'closed'},
            content_type='application/json',
        )
        assert resp.status_code == 400
        bug.refresh_from_db()
        assert bug.status == 'new'  # 未变

    def test_fix_records_fixer(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(
            project=test_project, title='X', status='fixing', reporter=test_user
        )
        auth_client.post(
            f'/api/bugs/{bug.id}/transition/',
            data={'to_status': 'fixed'},
            content_type='application/json',
        )
        bug.refresh_from_db()
        assert bug.fixer == test_user

    def test_close_sets_closed_at(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(
            project=test_project, title='X', status='verifying', reporter=test_user
        )
        auth_client.post(
            f'/api/bugs/{bug.id}/transition/',
            data={'to_status': 'closed'},
            content_type='application/json',
        )
        bug.refresh_from_db()
        assert bug.status == 'closed'
        assert bug.closed_at is not None

    def test_reopen_clears_closed_at(self, auth_client, test_project, test_user):
        from django.utils import timezone
        bug = Bug.objects.create(
            project=test_project, title='X', status='closed',
            reporter=test_user, closed_at=timezone.now(),
        )
        auth_client.post(
            f'/api/bugs/{bug.id}/transition/',
            data={'to_status': 'reopened'},
            content_type='application/json',
        )
        bug.refresh_from_db()
        assert bug.status == 'reopened'
        assert bug.closed_at is None


@pytest.mark.django_db
class TestBugAssign:
    def test_assign_from_new_auto_transitions_to_assigned(
        self, auth_client, test_project, test_user, test_password
    ):
        dev = User.objects.create_user(username='dev', password=test_password)
        test_project.members.add(dev)
        bug = Bug.objects.create(project=test_project, title='X', reporter=test_user)
        resp = auth_client.post(
            f'/api/bugs/{bug.id}/assign/',
            data={'user_id': dev.id},
            content_type='application/json',
        )
        assert resp.status_code == 200
        bug.refresh_from_db()
        assert bug.assignee == dev
        assert bug.status == 'assigned'

    def test_assign_in_fixing_keeps_status(
        self, auth_client, test_project, test_user, test_password
    ):
        dev = User.objects.create_user(username='dev', password=test_password)
        bug = Bug.objects.create(
            project=test_project, title='X', status='fixing', reporter=test_user
        )
        auth_client.post(
            f'/api/bugs/{bug.id}/assign/',
            data={'user_id': dev.id},
            content_type='application/json',
        )
        bug.refresh_from_db()
        assert bug.status == 'fixing'  # 状态不变
    def test_assign_rejects_user_outside_bug_project(
        self, auth_client, test_project, test_user, test_password
    ):
        outsider = User.objects.create_user(username='outside_dev', password=test_password)
        bug = Bug.objects.create(project=test_project, title='X', reporter=test_user)
        initial_transition_count = BugTransition.objects.count()

        resp = auth_client.post(
            f'/api/bugs/{bug.id}/assign/',
            data={'user_id': outsider.id},
            content_type='application/json',
        )

        assert resp.status_code == 403
        bug.refresh_from_db()
        assert bug.assignee is None
        assert bug.status == 'new'
        assert BugTransition.objects.count() == initial_transition_count


@pytest.mark.django_db
class TestBugComments:
    def test_add_and_list_comments(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(project=test_project, title='X', reporter=test_user)

        # 加
        resp = auth_client.post(
            f'/api/bugs/{bug.id}/comments/',
            data={'content': '这个 bug 我也遇到了'},
            content_type='application/json',
        )
        assert resp.status_code == 201

        # 查
        resp = auth_client.get(f'/api/bugs/{bug.id}/comments/')
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]['content'] == '这个 bug 我也遇到了'

    def test_empty_comment_rejected(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(project=test_project, title='X', reporter=test_user)
        resp = auth_client.post(
            f'/api/bugs/{bug.id}/comments/',
            data={'content': '   '},
            content_type='application/json',
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestBugMy:
    def test_my_assigned(self, auth_client, test_project, test_user, test_password):
        other = User.objects.create_user(username='other', password=test_password)
        Bug.objects.create(project=test_project, title='Mine', reporter=other, assignee=test_user)
        Bug.objects.create(project=test_project, title='NotMine', reporter=other, assignee=other)
        resp = auth_client.get('/api/bugs/my/?role=assignee')
        assert resp.status_code == 200
        data = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        titles = [b['title'] for b in data]
        assert 'Mine' in titles and 'NotMine' not in titles


@pytest.mark.django_db
class TestBugDetailIncludesTransitions:
    def test_detail_returns_allowed_transitions(self, auth_client, test_project, test_user):
        bug = Bug.objects.create(project=test_project, title='X', reporter=test_user)
        resp = auth_client.get(f'/api/bugs/{bug.id}/')
        assert resp.status_code == 200
        assert set(resp.data['allowed_transitions']) == {'confirmed', 'rejected', 'assigned'}


@pytest.mark.django_db
class TestBugStats:
    def test_stats_basic(self, auth_client, test_project, test_user):
        Bug.objects.create(project=test_project, title='A', status='new', reporter=test_user)
        Bug.objects.create(project=test_project, title='B', status='fixing', reporter=test_user)
        Bug.objects.create(
            project=test_project, title='C', status='closed', reporter=test_user
        )
        resp = auth_client.get(f'/api/bugs/stats/?project={test_project.id}')
        assert resp.status_code == 200
        assert resp.data['total'] == 3
        assert resp.data['open'] == 2  # closed 不算
        assert resp.data['closed'] == 1
        assert resp.data['by_status']['new'] == 1
