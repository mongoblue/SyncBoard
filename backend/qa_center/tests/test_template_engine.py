import pytest
from qa_center import template_engine as te


class TestBuildVariablePool:
    def test_overrides_highest_priority(self, db, mock_environment, mock_global_var):
        overrides = {"api_key": "override-value"}
        pool = te.build_variable_pool(
            environment=mock_environment,
            global_vars=[mock_global_var],
            overrides=overrides,
        )
        assert pool["api_key"] == "override-value"

    def test_environment_over_global(self, db, mock_environment, mock_global_var):
        pool = te.build_variable_pool(
            environment=mock_environment,
            global_vars=[mock_global_var],
        )
        assert pool["api_key"] == "test-key-123"

    def test_global_var_in_pool(self, db, mock_global_var):
        pool = te.build_variable_pool(global_vars=[mock_global_var])
        assert pool["global_token"] == "global-token-value"

    def test_base_url_exposed(self, db, mock_environment):
        pool = te.build_variable_pool(environment=mock_environment)
        assert pool["base_url"] == "https://httpbin.org"

    def test_empty_all(self):
        pool = te.build_variable_pool()
        assert pool == {}


class TestRenderString:
    def test_simple_substitution(self):
        result = te.render_string("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_missing_variable_preserved(self):
        result = te.render_string("Hello {{missing}}", {})
        assert result == "Hello {{missing}}"

    def test_whitespace_in_placeholder(self):
        result = te.render_string("{{  name  }}", {"name": "Bob"})
        assert result == "Bob"

    def test_multiple_placeholders(self):
        result = te.render_string("{{greeting}} {{name}}!", {"greeting": "Hi", "name": "Tom"})
        assert result == "Hi Tom!"

    def test_numeric_value_stringified(self):
        result = te.render_string("Count: {{count}}", {"count": 42})
        assert result == "Count: 42"

    def test_bool_value_stringified(self):
        result = te.render_string("Flag: {{flag}}", {"flag": True})
        assert result == "Flag: True"


class TestRenderValue:
    def test_nested_dict(self):
        result = te.render_value({"key": "{{val}}"}, {"val": "nested"})
        assert result == {"key": "nested"}

    def test_nested_list(self):
        result = te.render_value(["{{a}}", "{{b}}"], {"a": "x", "b": "y"})
        assert result == ["x", "y"]

    def test_standalone_placeholder_stringifies(self):
        result = te.render_value("{{count}}", {"count": 42})
        assert result == "42"
