"""
API 测试断言引擎
支持 JSONPath 断言和状态码断言
"""

import json
from typing import Any, List, Dict, Optional
from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.exceptions import JsonPathParserError


class AssertionEngine:
    """断言引擎"""
    
    # 支持的运算符
    OPERATORS = {
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
        '>': lambda a, b: a is not None and b is not None and a > b,
        '<': lambda a, b: a is not None and b is not None and a < b,
        '>=': lambda a, b: a is not None and b is not None and a >= b,
        '<=': lambda a, b: a is not None and b is not None and a <= b,
        'contains': lambda a, b: b in a if a is not None and b is not None else False,
        'exists': lambda a, b: a is not None,
    }
    
    @classmethod
    def evaluate_assertions(
        cls,
        assertions: List[Dict],
        status_code: int,
        response_body: str,
        response_headers: Dict
    ) -> List[Dict]:
        """
        执行所有断言
        
        Args:
            assertions: 断言配置列表
            status_code: HTTP 状态码
            response_body: 响应体字符串
            response_headers: 响应头字典
            
        Returns:
            断言结果列表，每个结果包含：
            - assertion: 原始断言配置
            - passed: 是否通过
            - actual_value: 实际值
            - message: 结果消息
        """
        results = []
        
        # 尝试解析响应体为 JSON
        response_json = None
        try:
            response_json = json.loads(response_body) if response_body else {}
        except json.JSONDecodeError:
            pass
        
        for assertion in assertions:
            result = cls._evaluate_single_assertion(
                assertion, status_code, response_json, response_body, response_headers
            )
            results.append(result)
        
        return results
    
    @classmethod
    def _evaluate_single_assertion(
        cls,
        assertion: Dict,
        status_code: int,
        response_json: Optional[Dict],
        response_body: str,
        response_headers: Dict
    ) -> Dict:
        """执行单个断言"""
        assertion_type = assertion.get('type', '')
        operator = assertion.get('operator', '==')
        expected_value = assertion.get('value')
        
        result = {
            'assertion': assertion,
            'passed': False,
            'actual_value': None,
            'message': ''
        }
        
        try:
            if assertion_type == 'status_code':
                result = cls._evaluate_status_code_assertion(
                    status_code, operator, expected_value
                )
            elif assertion_type == 'jsonpath':
                expression = assertion.get('expression', '')
                result = cls._evaluate_jsonpath_assertion(
                    response_json, response_body, expression, operator, expected_value
                )
            elif assertion_type == 'header':
                header_name = assertion.get('header_name', '')
                result = cls._evaluate_header_assertion(
                    response_headers, header_name, operator, expected_value
                )
            else:
                result['message'] = f'不支持的断言类型: {assertion_type}'
                
        except Exception as e:
            result['message'] = f'断言执行错误: {str(e)}'
        
        return result
    
    @classmethod
    def _evaluate_status_code_assertion(
        cls,
        status_code: int,
        operator: str,
        expected_value: Any
    ) -> Dict:
        """评估状态码断言"""
        result = {
            'assertion': {'type': 'status_code', 'operator': operator, 'value': expected_value},
            'passed': False,
            'actual_value': status_code,
            'message': ''
        }
        
        if operator not in cls.OPERATORS:
            result['message'] = f'不支持的运算符: {operator}'
            return result
        
        # 转换期望值为整数
        try:
            expected_int = int(expected_value) if expected_value is not None else None
        except (ValueError, TypeError):
            result['message'] = f'期望值必须是整数: {expected_value}'
            return result
        
        passed = cls.OPERATORS[operator](status_code, expected_int)
        result['passed'] = passed
        
        if passed:
            result['message'] = f'状态码 {status_code} {operator} {expected_int}'
        else:
            result['message'] = f'状态码断言失败: 实际 {status_code}, 期望 {operator} {expected_int}'
        
        return result
    
    @classmethod
    def _evaluate_jsonpath_assertion(
        cls,
        response_json: Optional[Dict],
        response_body: str,
        expression: str,
        operator: str,
        expected_value: Any
    ) -> Dict:
        """评估 JSONPath 断言"""
        result = {
            'assertion': {'type': 'jsonpath', 'expression': expression, 'operator': operator, 'value': expected_value},
            'passed': False,
            'actual_value': None,
            'message': ''
        }
        
        if response_json is None:
            result['message'] = '响应体不是有效的 JSON'
            return result
        
        if operator not in cls.OPERATORS:
            result['message'] = f'不支持的运算符: {operator}'
            return result
        
        try:
            jsonpath_expr = jsonpath_parse(expression)
            matches = jsonpath_expr.find(response_json)
            
            if not matches:
                actual_value = None
            elif len(matches) == 1:
                actual_value = matches[0].value
            else:
                actual_value = [match.value for match in matches]
            
            result['actual_value'] = actual_value
            
            # 特殊处理 exists 运算符
            if operator == 'exists':
                passed = actual_value is not None
                result['passed'] = passed
                result['message'] = f'路径 {expression} {"存在" if passed else "不存在"}'
                return result
            
            # 其他运算符
            passed = cls.OPERATORS[operator](actual_value, expected_value)
            result['passed'] = passed
            
            if passed:
                result['message'] = f'JSONPath {expression}: {actual_value} {operator} {expected_value}'
            else:
                result['message'] = f'JSONPath 断言失败: {expression} 实际值 {actual_value}, 期望 {operator} {expected_value}'
                
        except JsonPathParserError as e:
            result['message'] = f'JSONPath 表达式错误: {expression} - {str(e)}'
        except Exception as e:
            result['message'] = f'JSONPath 执行错误: {str(e)}'
        
        return result
    
    @classmethod
    def _evaluate_header_assertion(
        cls,
        response_headers: Dict,
        header_name: str,
        operator: str,
        expected_value: Any
    ) -> Dict:
        """评估响应头断言"""
        result = {
            'assertion': {'type': 'header', 'header_name': header_name, 'operator': operator, 'value': expected_value},
            'passed': False,
            'actual_value': None,
            'message': ''
        }
        
        if operator not in cls.OPERATORS:
            result['message'] = f'不支持的运算符: {operator}'
            return result
        
        # 响应头名称大小写不敏感
        actual_value = None
        for key, value in response_headers.items():
            if key.lower() == header_name.lower():
                actual_value = value
                break
        
        result['actual_value'] = actual_value
        
        # 特殊处理 exists 运算符
        if operator == 'exists':
            passed = actual_value is not None
            result['passed'] = passed
            result['message'] = f'响应头 {header_name} {"存在" if passed else "不存在"}'
            return result
        
        passed = cls.OPERATORS[operator](actual_value, expected_value)
        result['passed'] = passed
        
        if passed:
            result['message'] = f'响应头 {header_name}: {actual_value} {operator} {expected_value}'
        else:
            result['message'] = f'响应头断言失败: {header_name} 实际值 {actual_value}, 期望 {operator} {expected_value}'
        
        return result
