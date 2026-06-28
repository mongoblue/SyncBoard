"""
Test Login - 登录模块接口测试
使用 pytest.mark.parametrize 从 YAML 读取测试数据
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from common.assertion_util import AssertionUtil
from common.yaml_util import YamlUtil


# ============================================================================
# 读取 YAML 测试数据
# ============================================================================

LOGIN_TEST_DATA = YamlUtil.read("data/login.yaml")
TEST_CASES = LOGIN_TEST_DATA.get("test_cases", [])


# ============================================================================
# 参数化测试用例
# ============================================================================

@pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc["name"] for tc in TEST_CASES])
def test_login(api_client, logger, test_case):
    """
    登录模块参数化测试

    Args:
        api_client: API 客户端 fixture (来自 conftest.py)
        logger: 日志记录器 fixture (来自 conftest.py)
        test_case: 从 YAML 读取的测试数据
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🧪 执行测试: {test_case['name']}")
    logger.info(f"📝 描述: {test_case.get('description', '无')}")
    logger.info(f"{'='*60}")

    request_config = test_case.get("request", {})
    expected_config = test_case.get("expected", {})

    method = request_config.get("method", "GET")
    path = request_config.get("path", "/")
    json_data = request_config.get("json")
    params = request_config.get("params")

    expected_status = expected_config.get("status_code", 200)
    assertions = expected_config.get("assertions", [])

    try:
        response = api_client.request(
            method=method,
            path=path,
            params=params,
            json_data=json_data
        )

        AssertionUtil.assert_status_code(response, expected_status)

        for assertion in assertions:
            assertion_type = assertion.get("type")
            assertion_path = assertion.get("path", "")
            assertion_header = assertion.get("header", "")
            expected_value = assertion.get("expected")
            max_ms = assertion.get("max_ms")

            if assertion_type == "status_code":
                AssertionUtil.assert_status_code(response, expected_value)

            elif assertion_type == "json_path_equals":
                AssertionUtil.assert_json_path_equals(
                    response,
                    json_path=assertion_path,
                    expected=expected_value
                )

            elif assertion_type == "json_path_exists":
                AssertionUtil.assert_json_path_exists(
                    response,
                    json_path=assertion_path
                )

            elif assertion_type == "json_path_contains":
                AssertionUtil.assert_json_path_contains(
                    response,
                    json_path=assertion_path,
                    expected=expected_value
                )

            elif assertion_type == "response_time":
                AssertionUtil.assert_response_time(response, max_ms or expected_value)

            elif assertion_type == "response_header_exists":
                AssertionUtil.assert_response_header_exists(
                    response,
                    header=assertion_header or assertion_path
                )

            elif assertion_type == "response_header_equals":
                AssertionUtil.assert_response_header_equals(
                    response,
                    header=assertion_header or assertion_path,
                    expected=expected_value
                )

        logger.info(f"✅ 测试通过: {test_case['name']}")

    except AssertionError as e:
        logger.error(f"❌ 测试失败: {test_case['name']}")
        logger.error(f"   错误: {str(e)}")
        raise

    except Exception as e:
        logger.exception(f"💥 测试异常: {test_case['name']}")
        raise


# ============================================================================
# 独立测试用例
# ============================================================================

class TestLoginIndependent:
    """独立登录测试用例"""

    def test_login_with_token_in_header(self, api_client, logger):
        """测试带 Token 的请求"""
        logger.info("测试带 Token 的请求")

        response = api_client.request(
            method="GET",
            path="/get",
            headers={"Authorization": "Bearer test_token_123"}
        )

        AssertionUtil.assert_status_code(response, 200)
        AssertionUtil.assert_json_path_exists(response, "headers.Authorization")

    def test_login_response_has_json_content(self, api_client, logger):
        """测试响应包含 JSON 内容"""
        logger.info("测试响应 JSON 内容")

        response = api_client.post("/post", json_data={
            "username": "test_user",
            "password": "test_pass"
        })

        AssertionUtil.assert_status_code(response, 200)
        AssertionUtil.assert_json_path_exists(response, "json")
        AssertionUtil.assert_json_path_equals(
            response,
            json_path="json.username",
            expected="test_user"
        )
