"""
Conftest - pytest 全局配置和 Fixtures
提供测试所需的公共 fixture 和钩子函数
"""
import pytest
import time
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from common.request_util import RequestUtil
from common.logger_util import LoggerUtil
from common.yaml_util import YamlUtil


# ============================================================================
# 全局配置
# ============================================================================

CONFIG = YamlUtil.read("data/test_data.yaml")
API_CONFIG = CONFIG.get("api", {})
BASE_URL = os.getenv("API_BASE_URL", API_CONFIG.get("base_url", "http://httpbin.org"))
TIMEOUT = API_CONFIG.get("timeout", 30)

LOGIN_CONFIG = CONFIG.get("login", {}).get("valid_user", {})


# ============================================================================
# Session Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def session_logger():
    """会话级日志记录器"""
    logger = LoggerUtil.get_logger(
        name="api_auto_test",
        log_dir="logs",
        level=20,
        console=True,
        file_handler=True
    )
    return logger


@pytest.fixture(scope="session")
def api_client(session_logger):
    """会话级 API 客户端"""
    client = RequestUtil(base_url=BASE_URL, timeout=TIMEOUT)
    yield client
    client.close()


@pytest.fixture(scope="session")
def logger(session_logger):
    """会话级日志记录器（兼容别名）"""
    return session_logger


# ============================================================================
# Pytest Hooks
# ============================================================================

def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "smoke: 冒烟测试用例")
    config.addinivalue_line("markers", "regression: 回归测试用例")
    config.addinivalue_line("markers", "login: 登录相关测试")
    config.addinivalue_line("markers", "project: 项目模块测试")
