"""
Utils - 工具函数
"""
import hashlib
import random
import string
from datetime import datetime
from typing import Any, Dict


class Utils:
    """通用工具函数"""

    @staticmethod
    def generate_random_string(length: int = 8) -> str:
        """生成随机字符串"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    @staticmethod
    def generate_random_email() -> str:
        """生成随机邮箱"""
        username = Utils.generate_random_string(10)
        return f"{username}@test.com"

    @staticmethod
    def md5(text: str) -> str:
        """MD5 加密"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    @staticmethod
    def timestamp() -> int:
        """获取当前时间戳（秒）"""
        return int(datetime.now().timestamp())

    @staticmethod
    def timestamp_ms() -> int:
        """获取当前时间戳（毫秒）"""
        return int(datetime.now().timestamp() * 1000)

    @staticmethod
    def format_time(format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """获取格式化当前时间"""
        return datetime.now().strftime(format_str)

    @staticmethod
    def deep_merge(dict1: Dict, dict2: Dict) -> Dict:
        """深度合并两个字典"""
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Utils.deep_merge(result[key], value)
            else:
                result[key] = value
        return result
