"""安全加固测试 — 敏感字段脱敏、代码注入防护。"""

import pytest
from qa_center.locust_runner import (
    _mask_sensitive,
    _SENSITIVE_HEADERS,
    _SENSITIVE_KEYS,
)


class TestSensitiveMasking:
    """验证敏感字段脱敏逻辑。"""

    def test_masks_authorization_header(self):
        headers = {'Authorization': 'Bearer secret-token-12345', 'Content-Type': 'application/json'}
        masked = _mask_sensitive(headers)
        assert masked['Authorization'] == '***'
        assert masked['Content-Type'] == 'application/json'

    def test_masks_cookie_header(self):
        headers = {'Cookie': 'sessionid=abc123', 'Set-Cookie': 'token=xyz'}
        masked = _mask_sensitive(headers)
        assert masked['Cookie'] == '***'
        assert masked['Set-Cookie'] == '***'

    def test_masks_x_api_key(self):
        headers = {'X-API-Key': 'key-12345', 'Accept': 'application/json'}
        masked = _mask_sensitive(headers)
        assert masked['X-API-Key'] == '***'

    def test_masks_token_and_password_keys(self):
        data = {
            'auth_config': {
                'type': 'bearer',
                'token': 'my-secret-token',
                'password': 'my-password',
            },
            'url': 'https://example.com',
        }
        masked = _mask_sensitive(data)
        assert masked['auth_config']['token'] == '***'
        assert masked['auth_config']['password'] == '***'
        assert masked['url'] == 'https://example.com'

    def test_masks_nested_sensitive_data(self):
        data = {
            'steps': [
                {'headers': {'Authorization': 'Bearer nested-secret'}},
                {'body': 'normal data'},
            ],
            'secret': 'top-secret',
        }
        masked = _mask_sensitive(data)
        assert masked['steps'][0]['headers']['Authorization'] == '***'
        assert masked['steps'][1]['body'] == 'normal data'
        assert masked['secret'] == '***'

    def test_preserves_non_sensitive_data(self):
        data = {
            'name': 'test-case',
            'url': 'https://api.example.com/v1/users',
            'method': 'GET',
            'concurrent_users': 10,
            'headers': {'Content-Type': 'application/json', 'Accept': '*/*'},
        }
        masked = _mask_sensitive(data)
        assert masked == data  # Nothing should change

    def test_handles_non_dict_input(self):
        assert _mask_sensitive('plain string') == 'plain string'
        assert _mask_sensitive(123) == 123
        assert _mask_sensitive(None) is None

    def test_masks_long_sensitive_strings(self):
        long_token = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.very-long-token-value-here-for-testing'
        data = {'Authorization': long_token}
        masked = _mask_sensitive(data)
        assert masked['Authorization'] == '***'


class TestSensitiveKeyDetection:
    """验证敏感 key 检测。"""

    def test_authorization_is_sensitive(self):
        from qa_center.locust_runner import _is_sensitive_key
        assert _is_sensitive_key('authorization') is True
        assert _is_sensitive_key('Authorization') is True
        assert _is_sensitive_key('AUTHORIZATION') is True

    def test_password_is_sensitive(self):
        from qa_center.locust_runner import _is_sensitive_key
        assert _is_sensitive_key('password') is True
        assert _is_sensitive_key('PASSWORD') is True

    def test_normal_keys_not_sensitive(self):
        from qa_center.locust_runner import _is_sensitive_key
        assert _is_sensitive_key('url') is False
        assert _is_sensitive_key('method') is False
        assert _is_sensitive_key('concurrent_users') is False
