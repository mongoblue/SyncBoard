from http.cookies import SimpleCookie

from performance.locustfile import SyncBoardUser


class FakeResponse:
    def __init__(self, status_code, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.cookies = SimpleCookie()
        self.cookies['csrftoken'] = 'csrf-123'
        self.posts = []
        self.gets = []

    def post(self, url, json=None, headers=None):
        self.posts.append({'url': url, 'json': json, 'headers': headers or {}})
        if url == '/api/auth/login/':
            return FakeResponse(200, {'id': 1, 'username': 'test_user'})
        if url == '/api/projects/':
            return FakeResponse(201, {'id': 42})
        if url == '/api/tasks/':
            return FakeResponse(201, {'id': 99})
        return FakeResponse(404, text='not found')

    def get(self, url, headers=None):
        self.gets.append({'url': url, 'headers': headers or {}})
        if url.startswith('/api/columns/'):
            return FakeResponse(200, [{'id': 7}])
        return FakeResponse(200, [])


def make_user():
    user = object.__new__(SyncBoardUser)
    user.client = FakeClient()
    return user


def test_on_start_uses_csrf_cookie_for_project_creation(monkeypatch):
    monkeypatch.setenv('LOCUST_USERNAME', 'test_user')
    monkeypatch.setenv('LOCUST_PASSWORD', 'password123')
    user = make_user()

    user.on_start()

    project_post = next(call for call in user.client.posts if call['url'] == '/api/projects/')
    assert project_post['headers']['X-CSRFToken'] == 'csrf-123'
    assert 'Authorization' not in project_post['headers']
    assert user.project_id == 42
    assert user.column_id == 7


def test_create_task_refreshes_csrf_header_from_cookie():
    user = make_user()
    user.column_id = 7
    user.client.cookies['csrftoken'] = 'csrf-456'

    user.create_task()

    task_post = next(call for call in user.client.posts if call['url'] == '/api/tasks/')
    assert task_post['headers']['X-CSRFToken'] == 'csrf-456'
    assert 'Authorization' not in task_post['headers']
