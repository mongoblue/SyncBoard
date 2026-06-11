"""模板渲染单测 —— M3.2。

不依赖 DB；只测纯函数。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qa_center import template_engine as te


class TestRenderString:
    def test_simple_substitution(self):
        assert te.render_string('Hello {{name}}', {'name': 'Alice'}) == 'Hello Alice'

    def test_multiple_vars(self):
        out = te.render_string('{{a}}+{{b}}={{c}}', {'a': 1, 'b': 2, 'c': 3})
        assert out == '1+2=3'

    def test_whitespace_inside_braces(self):
        assert te.render_string('Hi {{  user_name  }}', {'user_name': 'Bob'}) == 'Hi Bob'

    def test_missing_var_kept_verbatim(self):
        assert te.render_string('Hi {{nope}}', {'name': 'x'}) == 'Hi {{nope}}'

    def test_none_value_becomes_empty(self):
        assert te.render_string('[{{x}}]', {'x': None}) == '[]'

    def test_no_placeholders_passthrough(self):
        assert te.render_string('plain text', {'a': 1}) == 'plain text'

    def test_empty_input(self):
        assert te.render_string('', {'a': 1}) == ''

    def test_invalid_name_not_replaced(self):
        # 不允许 {{1abc}}：占位符必须以字母/下划线开头
        assert te.render_string('{{1abc}}', {'1abc': 'x'}) == '{{1abc}}'


class TestRenderValue:
    def test_dict_deep(self):
        out = te.render_value({'k': 'v-{{x}}', 'nested': {'a': '{{x}}'}}, {'x': '42'})
        assert out == {'k': 'v-42', 'nested': {'a': '42'}}

    def test_list(self):
        out = te.render_value(['a', '{{x}}', 3], {'x': 'b'})
        assert out == ['a', 'b', 3]

    def test_non_string_passthrough(self):
        assert te.render_value(123, {'x': 'y'}) == 123
        assert te.render_value(True, {}) is True
        assert te.render_value(None, {}) is None

    def test_dict_keys_also_rendered(self):
        out = te.render_value({'{{k}}': 1}, {'k': 'foo'})
        assert out == {'foo': 1}


class TestResolveUrl:
    def test_absolute_url_no_base(self):
        assert te.resolve_url('https://x.com/api', {}) == 'https://x.com/api'

    def test_absolute_url_with_base(self):
        # 完整 URL 不会被 base_url 覆盖
        out = te.resolve_url('https://x.com/api', {'base_url': 'https://wrong.com'})
        assert out == 'https://x.com/api'

    def test_relative_with_base(self):
        out = te.resolve_url('/v1/foo', {'base_url': 'https://api.example.com/'})
        assert out == 'https://api.example.com/v1/foo'

    def test_relative_no_leading_slash(self):
        out = te.resolve_url('v1/foo', {'base_url': 'https://api.example.com'})
        assert out == 'https://api.example.com/v1/foo'

    def test_relative_no_base(self):
        # 没 base_url 时原样返回
        assert te.resolve_url('/v1/foo', {}) == '/v1/foo'

    def test_substitution_in_path(self):
        out = te.resolve_url('/v1/users/{{user_id}}', {'base_url': 'https://x.com', 'user_id': 7})
        assert out == 'https://x.com/v1/users/7'

    def test_empty_url(self):
        assert te.resolve_url('', {'base_url': 'https://x.com'}) == ''


class TestBuildVariablePool:
    def test_globals_only(self):
        gv = [SimpleNamespace(key='a', value='1'), SimpleNamespace(key='b', value='2')]
        pool = te.build_variable_pool(global_vars=gv)
        assert pool == {'a': '1', 'b': '2'}

    def test_env_overrides_global(self):
        gv = [SimpleNamespace(key='token', value='global-tok')]
        env = SimpleNamespace(variables={'token': 'env-tok'}, base_url='')
        pool = te.build_variable_pool(environment=env, global_vars=gv)
        assert pool['token'] == 'env-tok'

    def test_overrides_beat_env(self):
        env = SimpleNamespace(variables={'token': 'env-tok'}, base_url='')
        pool = te.build_variable_pool(environment=env, overrides={'token': 'runtime'})
        assert pool['token'] == 'runtime'

    def test_base_url_exposed(self):
        env = SimpleNamespace(variables={}, base_url='https://x.com')
        pool = te.build_variable_pool(environment=env)
        assert pool['base_url'] == 'https://x.com'

    def test_env_variables_can_override_base_url(self):
        # 环境 variables 里如果显式写了 base_url，要赢
        env = SimpleNamespace(variables={'base_url': 'https://override.com'}, base_url='https://default.com')
        pool = te.build_variable_pool(environment=env)
        assert pool['base_url'] == 'https://override.com'

    def test_empty_inputs(self):
        assert te.build_variable_pool() == {}


class TestFindUnresolved:
    def test_returns_names(self):
        assert te.find_unresolved('{{a}}{{b}}{{a}}') == ['a', 'b']

    def test_empty(self):
        assert te.find_unresolved('') == []
        assert te.find_unresolved('no vars here') == []
