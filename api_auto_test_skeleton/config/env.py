"""
Env - 环境配置
管理不同测试环境的配置信息
"""
import os
from enum import Enum


class Env(Enum):
    """测试环境枚举"""
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class EnvConfig:
    """环境配置类"""

    _configs = {
        Env.DEV: {
            "base_url": "http://dev-api.example.com",
            "db_host": "dev-db.example.com",
            "db_port": 3306,
        },
        Env.TEST: {
            "base_url": "http://test-api.example.com",
            "db_host": "test-db.example.com",
            "db_port": 3306,
        },
        Env.STAGING: {
            "base_url": "http://staging-api.example.com",
            "db_host": "staging-db.example.com",
            "db_port": 3306,
        },
        Env.PROD: {
            "base_url": "https://api.example.com",
            "db_host": "prod-db.example.com",
            "db_port": 3306,
        },
    }

    def __init__(self, env: Env = Env.TEST):
        self.env = env
        self.config = self._configs.get(env, self._configs[Env.TEST])

    @property
    def base_url(self) -> str:
        return self.config["base_url"]

    @property
    def db_host(self) -> str:
        return self.config["db_host"]

    @property
    def db_port(self) -> int:
        return self.config["db_port"]

    @classmethod
    def from_env(cls) -> "EnvConfig":
        """从环境变量读取"""
        env_str = os.getenv("TEST_ENV", "test").lower()
        try:
            env = Env(env_str)
        except ValueError:
            env = Env.TEST
        return cls(env)
