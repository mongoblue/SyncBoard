# backend/tests/test_curl.py
import pytest
from qa_center.utils.curl import to_curl


def test_to_curl_get():
    result = to_curl('GET', 'https://api.example.com/users', {}, None)
    assert 'curl -X GET' in result
    assert "'https://api.example.com/users'" in result
    assert '-d' not in result  # GET 不应有 body


def test_to_curl_post_json():
    headers = {'Authorization': 'Bearer abc', 'X-Custom': 'val'}
    body = {'name': 'test', 'count': 30}
    result = to_curl('POST', 'https://api.example.com/users', headers, body)
    assert 'curl -X POST' in result
    assert "Content-Type: application/json" in result
    assert 'Authorization: Bearer abc' in result
    assert '"name": "test"' in result or '"name":"test"' in result
    assert "'https://api.example.com/users'" in result


def test_to_curl_skips_cookie_header():
    """cookie 头不应该出现在 cURL 里"""
    headers = {'Cookie': 'sessionid=xyz', 'Authorization': 'Bearer abc'}
    result = to_curl('GET', 'https://api.example.com', headers, None)
    assert 'Cookie' not in result
    assert 'sessionid' not in result
    assert 'Authorization: Bearer abc' in result


def test_to_curl_form_urlencoded():
    body = {'username': 'admin', 'password': 'pass'}
    result = to_curl('POST', 'https://api.example.com/login', {},
                     body, content_type='application/x-www-form-urlencoded')
    assert 'username=admin' in result
    assert 'password=pass' in result


def test_to_curl_multipart():
    body = {'file_field': '/tmp/test.txt', 'description': 'a file'}
    result = to_curl('POST', 'https://api.example.com/upload', {},
                     body, content_type='multipart/form-data')
    assert '-F' in result
    assert 'file_field=/tmp/test.txt' in result


def test_to_curl_handles_chinese():
    headers = {'X-Name': '张三'}
    result = to_curl('GET', 'https://api.example.com', headers, None)
    assert '张三' in result
