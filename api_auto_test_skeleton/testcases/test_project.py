"""
Test Project - 项目模块接口测试
使用 pytest.mark.parametrize 从 YAML 读取测试数据
支持新增、查询、更新、删除接口测试
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from common.request_util import RequestUtil
from common.assertion_util import AssertionUtil
from common.yaml_util import YamlUtil


# ============================================================================
# 读取 YAML 测试数据
# ============================================================================

PROJECT_TEST_DATA = YamlUtil.read("data/project.yaml")
BASE_URL = PROJECT_TEST_DATA.get("base_url", "https://jsonplaceholder.typicode.com")
TEST_CASES = PROJECT_TEST_DATA.get("test_cases", [])


# ============================================================================
# Fixture: 使用 JSONPlaceholder API 的客户端
# ============================================================================

@pytest.fixture(scope="session")
def jsonplaceholder_client():
    """使用 JSONPlaceholder API 的客户端"""
    client = RequestUtil(base_url="https://jsonplaceholder.typicode.com", timeout=30)
    yield client
    client.close()


# ============================================================================
# 参数化测试用例
# ============================================================================

@pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc["name"] for tc in TEST_CASES])
def test_project_crud(jsonplaceholder_client, logger, test_case):
    """
    项目模块 CRUD 参数化测试

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
        response = jsonplaceholder_client.request(
            method=method,
            path=path,
            params=params,
            json_data=json_data
        )

        AssertionUtil.assert_status_code(response, expected_status)

        for assertion in assertions:
            assertion_type = assertion.get("type")
            assertion_path = assertion.get("path", "")
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
                AssertionUtil.assert_response_time(response, max_ms or 5000)

        logger.info(f"✅ 测试通过: {test_case['name']}")

    except AssertionError as e:
        logger.error(f"❌ 测试失败: {test_case['name']}")
        logger.error(f"   错误: {str(e)}")
        raise

    except Exception as e:
        logger.exception(f"💥 测试异常: {test_case['name']}")
        raise


# ============================================================================
# 独立测试用例 - 完整 CRUD 流程
# ============================================================================

class TestProjectCRUDFlow:
    """项目模块完整 CRUD 流程测试"""

    @pytest.fixture(scope="class")
    def project_client(self, jsonplaceholder_client):
        """使用 JSONPlaceholder API 的客户端"""
        return jsonplaceholder_client

    def test_01_create_project(self, project_client, logger):
        """步骤1: 创建项目"""
        logger.info("步骤1: 创建项目")

        response = project_client.post("/posts", json_data={
            "title": "新项目-AutoTest",
            "body": "这是自动化测试创建的项目",
            "userId": 1
        })

        AssertionUtil.assert_status_code(response, 201)
        AssertionUtil.assert_json_path_exists(response, "id")

        project_id = response.json().get("id")
        logger.info(f"   创建的项目ID: {project_id}")

        project_client._created_project_id = project_id

    def test_02_get_project(self, project_client, logger):
        """步骤2: 查询刚创建的项目"""
        logger.info("步骤2: 查询项目")

        project_id = getattr(project_client, "_created_project_id", 1)

        response = project_client.get(f"/posts/{project_id}")

        AssertionUtil.assert_status_code(response, 200)
        AssertionUtil.assert_json_path_equals(response, "id", project_id)

    def test_03_update_project(self, project_client, logger):
        """步骤3: 更新项目"""
        logger.info("步骤3: 更新项目")

        project_id = getattr(project_client, "_created_project_id", 1)

        response = project_client.put(f"/posts/{project_id}", json_data={
            "id": project_id,
            "title": "更新后的项目标题",
            "body": "更新后的项目描述",
            "userId": 1
        })

        AssertionUtil.assert_status_code(response, 200)
        AssertionUtil.assert_json_path_equals(response, "title", "更新后的项目标题")

    def test_04_delete_project(self, project_client, logger):
        """步骤4: 删除项目"""
        logger.info("步骤4: 删除项目")

        project_id = getattr(project_client, "_created_project_id", 1)

        response = project_client.delete(f"/posts/{project_id}")

        AssertionUtil.assert_status_code(response, 200)


class TestProjectEdgeCases:
    """项目模块边界测试"""

    def test_empty_title(self, jsonplaceholder_client, logger):
        """测试空标题"""
        logger.info("测试空标题")

        response = jsonplaceholder_client.post("/posts", json_data={
            "title": "",
            "body": "描述内容",
            "userId": 1
        })

        AssertionUtil.assert_status_code(response, 201)

    def test_special_characters_in_title(self, jsonplaceholder_client, logger):
        """测试标题包含特殊字符"""
        logger.info("测试特殊字符标题")

        response = jsonplaceholder_client.post("/posts", json_data={
            "title": "项目测试 <>&\"' 特殊字符",
            "body": "描述内容",
            "userId": 1
        })

        AssertionUtil.assert_status_code(response, 201)
        AssertionUtil.assert_json_path_equals(
            response,
            "title",
            "项目测试 <>&\"' 特殊字符"
        )

    def test_response_time_under_threshold(self, jsonplaceholder_client, logger):
        """测试响应时间在阈值内"""
        logger.info("测试响应时间")

        response = jsonplaceholder_client.get("/posts", params={"_limit": 10})

        AssertionUtil.assert_status_code(response, 200)
        AssertionUtil.assert_response_time(response, 30000)
