"""
Settings - 项目设置
全局配置项
"""
from config.env import EnvConfig, Env

env_config = EnvConfig.from_env()

BASE_URL = env_config.base_url
TIMEOUT = 30
VERIFY_SSL = False

LOG_LEVEL = "INFO"
LOG_TO_FILE = True
LOG_DIR = "logs"

DB_CONFIG = {
    "host": env_config.db_host,
    "port": env_config.db_port,
    "user": "test_user",
    "password": "test_password",
    "database": "test_db",
}

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
