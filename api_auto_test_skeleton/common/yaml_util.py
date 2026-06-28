"""
YAML Util - YAML 测试数据读取工具
支持读取单个 YAML 文件和整个目录
自动处理环境变量替换
"""
import os
import yaml
from typing import Any, Dict, List, Optional
from pathlib import Path


class YamlUtil:
    """YAML 测试数据读取工具"""

    _cache: Dict[str, Any] = {}

    @classmethod
    def read(
        cls,
        file_path: str,
        use_cache: bool = True,
        encoding: str = "utf-8"
    ) -> Dict | List:
        """
        读取单个 YAML 文件

        Args:
            file_path: YAML 文件路径（绝对路径或相对路径）
            use_cache: 是否使用缓存，默认为 True
            encoding: 文件编码，默认为 utf-8

        Returns:
            YAML 文件内容（dict 或 list）

        Example:
            data = YamlUtil.read("data/login.yaml")
            print(data["username"])
        """
        abs_path = cls._get_abs_path(file_path)

        if use_cache and abs_path in cls._cache:
            return cls._cache[abs_path]

        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"YAML 文件不存在: {abs_path}")

        with open(abs_path, "r", encoding=encoding) as f:
            content = yaml.safe_load(f)

        if use_cache:
            cls._cache[abs_path] = content

        return content

    @classmethod
    def read_all(
        cls,
        dir_path: str,
        pattern: str = "*.yaml",
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        读取目录下所有 YAML 文件

        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式，默认为 "*.yaml"
            use_cache: 是否使用缓存

        Returns:
            文件名(不含扩展名) -> 内容 的字典

        Example:
            all_data = YamlUtil.read_all("data/")
            print(all_data["login"]["username"])
        """
        abs_dir = cls._get_abs_path(dir_path)

        if not os.path.exists(abs_dir):
            raise FileNotFoundError(f"目录不存在: {abs_dir}")

        result = {}
        path_obj = Path(abs_dir)

        for yaml_file in path_obj.glob(pattern):
            key = yaml_file.stem
            result[key] = cls.read(str(yaml_file), use_cache=use_cache)

        for yaml_file in path_obj.glob("*.yml"):
            key = yaml_file.stem
            if key not in result:
                result[key] = cls.read(str(yaml_file), use_cache=use_cache)

        return result

    @classmethod
    def get(
        cls,
        file_path: str,
        *keys: str,
        default: Any = None,
        use_cache: bool = True
    ) -> Any:
        """
        从 YAML 文件中获取指定路径的值

        Args:
            file_path: YAML 文件路径
            *keys: 多级键路径，如 "data", "user", "name"
            default: 默认值，当路径不存在时返回
            use_cache: 是否使用缓存

        Returns:
            指定路径的值，不存在则返回默认值

        Example:
            username = YamlUtil.get("data/config.yaml", "login", "username")
            token = YamlUtil.get("data/config.yaml", "auth", "token", default="")
        """
        data = cls.read(file_path, use_cache=use_cache)

        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return default
            elif isinstance(current, list):
                try:
                    index = int(key)
                    current = current[index] if index < len(current) else None
                except (ValueError, IndexError):
                    return default
            else:
                return default

        return current if current is not None else default

    @classmethod
    def clear_cache(cls):
        """清空缓存"""
        cls._cache.clear()

    @staticmethod
    def _get_abs_path(path: str) -> str:
        """获取绝对路径"""
        if os.path.isabs(path):
            return path
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(current_dir, path)

    @classmethod
    def dump(
        cls,
        data: Dict | List,
        file_path: str,
        encoding: str = "utf-8"
    ):
        """
        将数据写入 YAML 文件

        Args:
            data: 要写入的数据
            file_path: 文件路径
            encoding: 编码
        """
        abs_path = cls._get_abs_path(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, "w", encoding=encoding) as f:
            yaml.dump(
                data,
                f,
                allow_unicode=True,
                sort_keys=False,
                indent=2
            )

    @staticmethod
    def replace_env_vars(data: Any) -> Any:
        """
        替换数据中的环境变量
        格式: ${ENV_VAR_NAME} 或 ${ENV_VAR_NAME:default_value}

        Args:
            data: 原始数据

        Returns:
            替换后的数据
        """
        if isinstance(data, str):
            import re
            pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'

            def replacer(match):
                var_name = match.group(1)
                default_value = match.group(2) or ""
                return os.environ.get(var_name, default_value)

            return re.sub(pattern, replacer, data)

        elif isinstance(data, dict):
            return {k: cls.replace_env_vars(v) for k, v in data.items()}

        elif isinstance(data, list):
            return [cls.replace_env_vars(item) for item in data]

        return data


if __name__ == "__main__":
    print("=" * 60)
    print("YamlUtil 使用示例")
    print("=" * 60)

    sample_data = {
        "name": "test_user",
        "age": 25,
        "address": {
            "city": "Beijing",
            "district": "Chaoyang"
        },
        "tags": ["python", "api", "testing"]
    }

    YamlUtil.dump(sample_data, "data/sample.yaml")
    print("已写入 sample.yaml")

    loaded = YamlUtil.read("data/sample.yaml")
    print(f"读取数据: {loaded}")

    city = YamlUtil.get("data/sample.yaml", "address", "city")
    print(f"获取 city: {city}")

    print("\n环境变量替换示例:")
    os.environ["TEST_ENV"] = "production"
    test_data = {"url": "${TEST_ENV:dev}_api.example.com"}
    replaced = YamlUtil.replace_env_vars(test_data)
    print(f"替换后: {replaced}")
