"""Extractor 单元测试 —— M3.3。

只测纯函数 extract_value / run_extractors / summarize_extractions，不依赖 DB。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qa_center import extractors as ex


# ---------- extract_value ----------


class TestExtractValue:
    def test_status_source(self):
        v = ex.extract_value(
            source='status', expression='',
            response_json=None, response_headers={}, status_code=201,
        )
        assert v == 201

    def test_response_time_source(self):
        v = ex.extract_value(
            source='response_time', expression='',
            response_json=None, response_headers={}, status_code=200,
            response_time_ms=42.5,
        )
        assert v == 42.5

    def test_header_case_insensitive(self):
        v = ex.extract_value(
            source='header', expression='x-trace-id',
            response_json=None, response_headers={'X-Trace-Id': 'abc'},
            status_code=200,
        )
        assert v == 'abc'

    def test_header_missing_returns_default(self):
        v = ex.extract_value(
            source='header', expression='X-Missing',
            response_json=None, response_headers={'X-Other': 'y'},
            status_code=200, default='fallback',
        )
        assert v == 'fallback'

    def test_cookie_lookup(self):
        v = ex.extract_value(
            source='cookie', expression='sessionid',
            response_json=None, response_headers={}, status_code=200,
            cookies={'sessionid': 'sess-1', 'csrftoken': 'tok-2'},
        )
        assert v == 'sess-1'

    def test_cookie_missing_returns_default(self):
        v = ex.extract_value(
            source='cookie', expression='nope',
            response_json=None, response_headers={}, status_code=200,
            cookies={}, default='-',
        )
        assert v == '-'

    def test_body_jsonpath_dot(self):
        v = ex.extract_value(
            source='body', expression='data.user.id',
            response_json={'data': {'user': {'id': 7}}},
            response_headers={}, status_code=200,
        )
        assert v == 7

    def test_body_jsonpath_with_prefix(self):
        v = ex.extract_value(
            source='body', expression='$.data.token',
            response_json={'data': {'token': 'tok-x'}},
            response_headers={}, status_code=200,
        )
        assert v == 'tok-x'

    def test_body_missing_path_returns_default(self):
        v = ex.extract_value(
            source='body', expression='data.nope',
            response_json={'data': {'user': {'id': 7}}},
            response_headers={}, status_code=200, default='miss',
        )
        assert v == 'miss'

    def test_body_no_json_returns_default(self):
        v = ex.extract_value(
            source='body', expression='data.id',
            response_json=None, response_headers={}, status_code=200,
            default='none',
        )
        assert v == 'none'

    def test_unknown_source_returns_default(self):
        v = ex.extract_value(
            source='nonsense', expression='x',
            response_json={}, response_headers={}, status_code=200,
            default='d',
        )
        assert v == 'd'


# ---------- run_extractors ----------


def _make_extractor(name, source, expression='', default='', is_active=True):
    return SimpleNamespace(
        name=name, source=source, expression=expression,
        default_value=default, is_active=is_active,
    )


class TestRunExtractors:
    def test_multiple_kinds(self):
        out = ex.run_extractors(
            [
                _make_extractor('uid', 'body', 'data.id'),
                _make_extractor('trace', 'header', 'X-Trace'),
                _make_extractor('code', 'status'),
                _make_extractor('took', 'response_time'),
            ],
            response_json={'data': {'id': 99}},
            response_headers={'X-Trace': 'abc'},
            status_code=200, response_time_ms=15,
        )
        assert out == {'uid': 99, 'trace': 'abc', 'code': 200, 'took': 15}

    def test_inactive_skipped(self):
        out = ex.run_extractors(
            [
                _make_extractor('a', 'status', is_active=True),
                _make_extractor('b', 'status', is_active=False),
            ],
            response_json=None, response_headers={}, status_code=204,
        )
        assert out == {'a': 204}

    def test_empty_name_skipped(self):
        out = ex.run_extractors(
            [_make_extractor('', 'status'), _make_extractor('  ', 'status')],
            response_json=None, response_headers={}, status_code=204,
        )
        assert out == {}

    def test_default_used_when_missing(self):
        out = ex.run_extractors(
            [_make_extractor('token', 'body', 'data.token', default='anon')],
            response_json={'data': {}}, response_headers={}, status_code=200,
        )
        assert out == {'token': 'anon'}

    def test_no_extractors_returns_empty(self):
        assert ex.run_extractors([], response_json=None, response_headers={}, status_code=200) == {}
        assert ex.run_extractors(None, response_json=None, response_headers={}, status_code=200) == {}


# ---------- summarize_extractions ----------


class TestSummarize:
    def test_basic(self):
        out = ex.summarize_extractions({'a': 1, 'b': 'hello'})
        assert {'name': 'a', 'value_preview': '1', 'is_none': False} in out
        assert {'name': 'b', 'value_preview': 'hello', 'is_none': False} in out

    def test_long_value_truncated(self):
        out = ex.summarize_extractions({'big': 'x' * 300})
        item = out[0]
        assert len(item['value_preview']) == 201  # 200 chars + ellipsis
        assert item['value_preview'].endswith('…')

    def test_none_marked(self):
        out = ex.summarize_extractions({'missing': None})
        assert out[0]['is_none'] is True
        assert out[0]['value_preview'] == ''
