"""
Assertion Util - 断言封装工具
封装常用断言方法，支持状态码、JSON 字段值、字段存在等断言
提供详细的断言失败信息
"""
import json
from typing import Any, Optional, List, Callable
from requests import Response


class AssertionUtil:
    """断言工具类"""

    @staticmethod
    def assert_status_code(
        response: Response,
        expected: int,
        msg: Optional[str] = None
    ):
        """
        断言 HTTP 状态码

        Args:
            response: requests.Response 对象
            expected: 期望的状态码
            msg: 自定义失败信息

        Raises:
            AssertionError: 断言失败时抛出

        Example:
            AssertionUtil.assert_status_code(response, 200)
        """
        actual = response.status_code
        if actual != expected:
            failure_msg = msg or f"❌ 状态码断言失败"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   期望: {expected}\n"
                f"   实际: {actual}"
            )

    @staticmethod
    def assert_in_status_codes(
        response: Response,
        expected_codes: List[int],
        msg: Optional[str] = None
    ):
        """
        断言状态码在指定列表中

        Args:
            response: requests.Response 对象
            expected_codes: 期望的状态码列表
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_in_status_codes(response, [200, 201, 204])
        """
        actual = response.status_code
        if actual not in expected_codes:
            failure_msg = msg or f"❌ 状态码断言失败"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   期望包含: {expected_codes}\n"
                f"   实际: {actual}"
            )

    @staticmethod
    def assert_json_path_equals(
        response: Response,
        json_path: str,
        expected: Any,
        msg: Optional[str] = None
    ):
        """
        断言 JSON 响应中指定路径的值等于预期值

        Args:
            response: requests.Response 对象
            json_path: JSON 路径，支持嵌套和数组索引
                      例如: "data.user.name" 或 "data.items[0].id"
            expected: 期望的值
            msg: 自定义失败信息

        Raises:
            AssertionError: 断言失败或 JSON 解析失败时抛出

        Example:
            AssertionUtil.assert_json_path_equals(response, "data.token", "abc123")
            AssertionUtil.assert_json_path_equals(response, "data.count", 10)
        """
        try:
            data = response.json()
        except json.JSONDecodeError:
            raise AssertionError(
                f"❌ JSON 解析失败\n"
                f"   响应内容: {response.text[:200]}"
            )

        actual = AssertionUtil._extract_json_path(data, json_path)

        if actual != expected:
            failure_msg = msg or f"❌ JSON 路径值断言失败"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   路径: {json_path}\n"
                f"   期望: {expected}\n"
                f"   实际: {actual}"
            )

    @staticmethod
    def assert_json_path_exists(
        response: Response,
        json_path: str,
        msg: Optional[str] = None
    ):
        """
        断言 JSON 响应中指定路径存在且值不为 None

        Args:
            response: requests.Response 对象
            json_path: JSON 路径
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_json_path_exists(response, "data.token")
        """
        try:
            data = response.json()
        except json.JSONDecodeError:
            raise AssertionError(
                f"❌ JSON 解析失败\n"
                f"   响应内容: {response.text[:200]}"
            )

        actual = AssertionUtil._extract_json_path(data, json_path)

        if actual is None:
            failure_msg = msg or f"❌ JSON 路径不存在"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   路径: {json_path}\n"
                f"   响应: {json.dumps(data, ensure_ascii=False)[:200]}"
            )

    @staticmethod
    def assert_json_path_not_exists(
        response: Response,
        json_path: str,
        msg: Optional[str] = None
    ):
        """
        断言 JSON 响应中指定路径不存在

        Args:
            response: requests.Response 对象
            json_path: JSON 路径
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_json_path_not_exists(response, "data.error")
        """
        try:
            data = response.json()
        except json.JSONDecodeError:
            return

        actual = AssertionUtil._extract_json_path(data, json_path)

        if actual is not None:
            failure_msg = msg or f"❌ JSON 路径不应存在"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   路径: {json_path}\n"
                f"   实际值: {actual}"
            )

    @staticmethod
    def assert_json_path_contains(
        response: Response,
        json_path: str,
        expected: Any,
        msg: Optional[str] = None
    ):
        """
        断言 JSON 响应中指定路径的值包含预期内容

        Args:
            response: requests.Response 对象
            json_path: JSON 路径
            expected: 期望包含的内容
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_json_path_contains(response, "data.message", "success")
        """
        try:
            data = response.json()
        except json.JSONDecodeError:
            raise AssertionError(f"❌ JSON 解析失败: {response.text[:200]}")

        actual = AssertionUtil._extract_json_path(data, json_path)

        if actual is None:
            raise AssertionError(
                f"❌ JSON 路径不存在\n"
                f"   路径: {json_path}"
            )

        expected_str = str(expected)
        actual_str = str(actual)

        if expected_str not in actual_str:
            failure_msg = msg or f"❌ JSON 路径值不包含预期内容"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   路径: {json_path}\n"
                f"   期望包含: {expected_str}\n"
                f"   实际值: {actual_str}"
            )

    @staticmethod
    def assert_json_path_matches(
        response: Response,
        json_path: str,
        regex_pattern: str,
        msg: Optional[str] = None
    ):
        """
        断言 JSON 响应中指定路径的值匹配正则表达式

        Args:
            response: requests.Response 对象
            json_path: JSON 路径
            regex_pattern: 正则表达式模式
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_json_path_matches(
                response, "data.email", r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            )
        """
        import re

        try:
            data = response.json()
        except json.JSONDecodeError:
            raise AssertionError(f"❌ JSON 解析失败: {response.text[:200]}")

        actual = AssertionUtil._extract_json_path(data, json_path)

        if actual is None:
            raise AssertionError(f"❌ JSON 路径不存在: {json_path}")

        if not re.match(regex_pattern, str(actual)):
            failure_msg = msg or f"❌ JSON 路径值不匹配正则"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   路径: {json_path}\n"
                f"   正则: {regex_pattern}\n"
                f"   实际值: {actual}"
            )

    @staticmethod
    def assert_response_time(
        response: Response,
        max_ms: int,
        msg: Optional[str] = None
    ):
        """
        断言响应时间在限制内

        Args:
            response: requests.Response 对象
            max_ms: 最大响应时间（毫秒）
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_response_time(response, 500)
        """
        elapsed_ms = response.elapsed.total_seconds() * 1000

        if elapsed_ms > max_ms:
            failure_msg = msg or f"❌ 响应时间超限"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   最大: {max_ms}ms\n"
                f"   实际: {elapsed_ms:.2f}ms"
            )

    @staticmethod
    def assert_response_header_exists(
        response: Response,
        header: str,
        msg: Optional[str] = None
    ):
        """
        断言响应头中存在指定的 header

        Args:
            response: requests.Response 对象
            header: 响应头名称（不区分大小写）
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_response_header_exists(response, "Content-Type")
        """
        header_lower = header.lower()
        headers = {k.lower(): v for k, v in response.headers.items()}

        if header_lower not in headers:
            failure_msg = msg or f"❌ 响应头不存在"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   期望Header: {header}\n"
                f"   实际Headers: {list(headers.keys())}"
            )

    @staticmethod
    def assert_response_header_equals(
        response: Response,
        header: str,
        expected: str,
        msg: Optional[str] = None
    ):
        """
        断言响应头中指定 header 的值等于预期

        Args:
            response: requests.Response 对象
            header: 响应头名称
            expected: 期望的值
            msg: 自定义失败信息

        Example:
            AssertionUtil.assert_response_header_equals(response, "Content-Type", "application/json")
        """
        actual = response.headers.get(header)
        if actual is None:
            raise AssertionError(f"❌ 响应头不存在: {header}")

        if actual != expected:
            failure_msg = msg or f"❌ 响应头值断言失败"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   Header: {header}\n"
                f"   期望: {expected}\n"
                f"   实际: {actual}"
            )

    @staticmethod
    def assert_response_not_empty(
        response: Response,
        msg: Optional[str] = None
    ):
        """
        断言响应体不为空

        Args:
            response: requests.Response 对象
            msg: 自定义失败信息
        """
        if not response.text or len(response.text.strip()) == 0:
            failure_msg = msg or f"❌ 响应体为空"
            raise AssertionError(failure_msg)

    @staticmethod
    def assert_response_equals(
        response: Response,
        expected: str,
        msg: Optional[str] = None
    ):
        """
        断言响应体文本等于预期值

        Args:
            response: requests.Response 对象
            expected: 期望的响应文本
            msg: 自定义失败信息
        """
        actual = response.text

        if actual != expected:
            failure_msg = msg or f"❌ 响应体文本断言失败"
            raise AssertionError(
                f"{failure_msg}\n"
                f"   期望: {expected}\n"
                f"   实际: {actual[:200]}"
            )

    @staticmethod
    def assert_true(
        condition: bool,
        msg: Optional[str] = None
    ):
        """
        通用断言：条件为 True

        Args:
            condition: 条件表达式
            msg: 自定义失败信息
        """
        if not condition:
            raise AssertionError(msg or "❌ 断言失败: 条件为 False")

    @staticmethod
    def assert_equal(
        actual: Any,
        expected: Any,
        msg: Optional[str] = None
    ):
        """
        通用断言：两个值相等

        Args:
            actual: 实际值
            expected: 期望值
            msg: 自定义失败信息
        """
        if actual != expected:
            raise AssertionError(
                (msg or "❌ 断言失败") + f"\n   期望: {expected}\n   实际: {actual}"
            )

    @staticmethod
    def _extract_json_path(data: Any, json_path: str) -> Any:
        """
        提取 JSON 路径对应的值

        Args:
            data: JSON 数据（dict 或 list）
            json_path: JSON 路径，支持格式:
                      - 嵌套: "data.user.name"
                      - 数组索引: "data.items[0].id"
                      - 混合: "data[0].name"

        Returns:
            路径对应的值，不存在返回 None
        """
        if not json_path:
            return data

        parts = AssertionUtil._parse_json_path(json_path)
        current = data

        for part in parts:
            if current is None:
                return None

            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    index = int(part)
                    current = current[index] if 0 <= index < len(current) else None
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return current

    @staticmethod
    def _parse_json_path(json_path: str) -> List[str]:
        """
        解析 JSON 路径为部件列表

        Args:
            json_path: JSON 路径字符串

        Returns:
            路径部件列表

        Example:
            "data.user.name" -> ["data", "user", "name"]
            "data.items[0].id" -> ["data", "items", "0", "id"]
        """
        import re
        pattern = r'\[(\d+)\]|\.'
        parts = re.split(pattern, json_path)
        return [p for p in parts if p]
