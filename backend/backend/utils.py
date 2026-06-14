"""
Django REST Framework 自定义异常处理器
提供结构化的错误响应，替代默认的 HTML 错误页面
"""

import logging
import traceback
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    自定义异常处理器
    将 Django 异常转换为结构化的 JSON 响应

    返回格式: {error: true, code: 'ERROR_CODE', message: '...', details?: {...}}
    """
    # 首先调用 REST framework 的默认异常处理器
    response = exception_handler(exc, context)

    if response is not None:
        # 提取错误消息和详情
        error_details = response.data
        if isinstance(error_details, dict) and 'detail' in error_details:
            error_message = error_details.pop('detail')
        else:
            error_message = _get_error_message(error_details)

        # 构建统一错误响应
        error_data = {
            'error': True,
            'code': _get_error_code(response.status_code),
            'message': error_message,
        }

        # 如果还有剩余的详情，添加到 details
        if error_details:
            error_data['details'] = error_details

        response.data = error_data
        return response

    # 处理未捕获的异常（如 AttributeError 等）
    # 记录详细的错误日志
    request = context.get('request')
    view = context.get('view')

    error_message = str(exc)
    error_type = type(exc).__name__
    error_traceback = traceback.format_exc()

    logger.error(
        f"未捕获的异常: {error_type}\n"
        f"请求路径: {request.path if request else 'Unknown'}\n"
        f"请求方法: {request.method if request else 'Unknown'}\n"
        f"视图: {view.__class__.__name__ if view else 'Unknown'}\n"
        f"错误信息: {error_message}\n"
        f"堆栈跟踪:\n{error_traceback}"
    )

    # 返回结构化的 JSON 错误响应，而不是 HTML 页面
    error_response = {
        'error': True,
        'code': 'INTERNAL_ERROR',
        'message': '服务器内部错误',
        'details': {
            'error_type': error_type,
        }
    }

    # 在 DEBUG 模式下添加更多调试信息
    from django.conf import settings
    if settings.DEBUG:
        error_response['details']['error_message'] = error_message
        error_response['details']['traceback'] = error_traceback.split('\n')

    return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _get_error_code(status_code):
    """根据状态码获取错误码"""
    code_mapping = {
        400: 'BAD_REQUEST',
        401: 'UNAUTHORIZED',
        403: 'PERMISSION_DENIED',
        404: 'NOT_FOUND',
        405: 'METHOD_NOT_ALLOWED',
        500: 'INTERNAL_ERROR',
    }
    return code_mapping.get(status_code, 'UNKNOWN_ERROR')


def _get_error_message(data):
    """从响应数据中提取错误消息"""
    if isinstance(data, dict):
        if 'detail' in data:
            return data['detail']
        if 'message' in data:
            return data['message']
        # 返回第一个错误消息
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            elif isinstance(value, str):
                return f"{key}: {value}"
    elif isinstance(data, list) and data:
        return str(data[0])
    elif isinstance(data, str):
        return data
    return '请求处理失败'
