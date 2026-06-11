"""请求构造辅助 request_builder 的纯函数测试 —— M3.4。

只测 normalize_query_params / build_file_tuples，不依赖 DB。
"""
from __future__ import annotations

import base64

import pytest

from qa_center import request_builder as rb


# ---------- normalize_query_params ----------


class TestNormalizeQueryParams:
    def test_none_returns_none(self):
        assert rb.normalize_query_params(None) is None

    def test_empty_dict_returns_none(self):
        assert rb.normalize_query_params({}) is None

    def test_empty_list_returns_none(self):
        assert rb.normalize_query_params([]) is None

    def test_dict_basic(self):
        out = rb.normalize_query_params({'page': 1, 'size': 20})
        # 顺序不强求；用 set 比较
        assert set(out) == {('page', '1'), ('size', '20')}

    def test_dict_with_list_value_expands(self):
        out = rb.normalize_query_params({'tag': ['a', 'b', 'c']})
        assert out == [('tag', 'a'), ('tag', 'b'), ('tag', 'c')]

    def test_list_of_pairs_keeps_order_and_duplicates(self):
        out = rb.normalize_query_params([['k', 'v1'], ['k', 'v2'], ['m', '1']])
        assert out == [('k', 'v1'), ('k', 'v2'), ('m', '1')]

    def test_list_of_dicts_with_name_value(self):
        out = rb.normalize_query_params([{'name': 'q', 'value': 'hello'}])
        assert out == [('q', 'hello')]

    def test_skips_unparseable_items(self):
        out = rb.normalize_query_params([['k', 'v'], 'oops', 123])
        assert out == [('k', 'v')]

    def test_bool_stringified_lowercase(self):
        out = rb.normalize_query_params({'flag': True, 'off': False})
        assert set(out) == {('flag', 'true'), ('off', 'false')}

    def test_none_value_becomes_empty_string(self):
        out = rb.normalize_query_params({'x': None})
        assert out == [('x', '')]

    def test_template_rendering(self):
        out = rb.normalize_query_params(
            {'page': '{{p}}', 'q': '{{kw}}'},
            variables={'p': '3', 'kw': 'hello world'},
        )
        assert set(out) == {('page', '3'), ('q', 'hello world')}

    def test_template_key_rendered(self):
        out = rb.normalize_query_params(
            [['{{key_name}}', 'v']], variables={'key_name': 'token'},
        )
        assert out == [('token', 'v')]

    def test_unsupported_type_returns_none(self):
        assert rb.normalize_query_params(42) is None
        assert rb.normalize_query_params('foo=bar') is None


# ---------- build_file_tuples ----------


class TestBuildFileTuples:
    def test_none_returns_none(self):
        assert rb.build_file_tuples(None) is None

    def test_empty_list_returns_none(self):
        assert rb.build_file_tuples([]) is None

    def test_dict_at_top_level_rejected(self):
        # 顶层应该是 list；dict 是结构错误
        assert rb.build_file_tuples({'name': 'a'}) is None

    def test_basic_text_content(self):
        out = rb.build_file_tuples([{
            'name': 'file', 'filename': 'a.txt',
            'content': 'hello', 'content_type': 'text/plain',
        }])
        assert out is not None and len(out) == 1
        field, (filename, content, ctype) = out[0]
        assert field == 'file'
        assert filename == 'a.txt'
        assert content == b'hello'
        assert ctype == 'text/plain'

    def test_default_content_type(self):
        out = rb.build_file_tuples([{
            'name': 'f', 'filename': 'x', 'content': 'y',
        }])
        assert out[0][1][2] == 'application/octet-stream'

    def test_default_filename_falls_back_to_name(self):
        out = rb.build_file_tuples([{'name': 'avatar', 'content': 'bin'}])
        assert out[0][1][0] == 'avatar'

    def test_base64_encoding(self):
        raw = b'\x00\x01\x02binary'
        out = rb.build_file_tuples([{
            'name': 'f', 'filename': 'b.bin',
            'content': base64.b64encode(raw).decode('ascii'),
            'encoding': 'base64',
            'content_type': 'application/octet-stream',
        }])
        assert out[0][1][1] == raw

    def test_invalid_base64_yields_empty(self):
        out = rb.build_file_tuples([{
            'name': 'f', 'filename': 'b.bin',
            'content': '@@@not-base64@@@', 'encoding': 'base64',
        }])
        assert out[0][1][1] == b''

    def test_skip_item_missing_name(self):
        out = rb.build_file_tuples([
            {'filename': 'noname.txt', 'content': 'x'},
            {'name': 'good', 'content': 'y'},
        ])
        assert len(out) == 1
        assert out[0][0] == 'good'

    def test_skip_non_dict_item(self):
        out = rb.build_file_tuples([
            'not a dict',
            {'name': 'good', 'content': 'y'},
        ])
        assert len(out) == 1

    def test_template_rendering_in_text_content(self):
        out = rb.build_file_tuples(
            [{'name': 'csv', 'filename': '{{kind}}.csv', 'content': 'id,{{val}}'}],
            variables={'kind': 'users', 'val': 'alice'},
        )
        field, (filename, content, _ctype) = out[0]
        assert filename == 'users.csv'
        assert content == b'id,alice'

    def test_template_not_applied_to_base64_content(self):
        # base64 内容里出现 {{xxx}} 不应被替换（会破坏编码）
        raw = b'sentinel'
        b64 = base64.b64encode(raw).decode('ascii')
        # 故意构造一个看似 base64 的字符串 - 确保渲染不会破坏它
        out = rb.build_file_tuples(
            [{'name': 'f', 'filename': 'a', 'content': b64, 'encoding': 'base64'}],
            variables={'whatever': 'x'},
        )
        assert out[0][1][1] == raw

    def test_field_alias_supported(self):
        out = rb.build_file_tuples([{'field': 'avatar', 'content': 'x'}])
        assert out[0][0] == 'avatar'

    def test_all_invalid_returns_none(self):
        assert rb.build_file_tuples(['a', 'b', {}]) is None
