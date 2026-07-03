import json
import pytest
from qa_center import extractors as ex


class TestExtractValue:
    def test_single_value(self):
        result = ex.extract_value(
            source="body",
            expression="$.name",
            response_json={"name": "Alice", "age": 30},
            response_headers={},
            status_code=200,
        )
        assert result == "Alice"

    def test_nested_value(self):
        result = ex.extract_value(
            source="body",
            expression="$.data.items[0].id",
            response_json={"data": {"items": [{"id": 1}, {"id": 2}]}},
            response_headers={},
            status_code=200,
        )
        assert result == 1

    def test_array_result(self):
        result = ex.extract_value(
            source="body",
            expression="$.tags[*]",
            response_json={"tags": ["a", "b", "c"]},
            response_headers={},
            status_code=200,
        )
        assert result == ["a", "b", "c"]

    def test_path_not_found(self):
        result = ex.extract_value(
            source="body",
            expression="$.nonexistent",
            response_json={"name": "test"},
            response_headers={},
            status_code=200,
        )
        assert result is None

    def test_status_source(self):
        result = ex.extract_value(
            source="status",
            expression="",
            response_json={},
            response_headers={},
            status_code=201,
        )
        assert result == 201


class TestChainedExtraction:
    def test_chain_two_steps(self):
        response1 = {"user": {"id": 42, "name": "Alice"}}
        user_id = ex.extract_value(
            source="body",
            expression="$.user.id",
            response_json=response1,
            response_headers={},
            status_code=200,
        )
        assert user_id == 42

        response2 = {
            "orders": [
                {"id": 1, "user_id": 42},
                {"id": 2, "user_id": 99},
            ]
        }
        # Get first order and verify user_id matches
        first_order = ex.extract_value(
            source="body",
            expression="$.orders[0]",
            response_json=response2,
            response_headers={},
            status_code=200,
        )
        assert first_order["user_id"] == 42
        assert first_order["id"] == 1
