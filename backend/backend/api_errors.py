"""
统一错误响应工具

提供标准化的错误响应格式：{error: true, code: 'ERROR_CODE', message: '...'}
"""

from rest_framework.response import Response
from rest_framework import status


class APIError:
    """错误码定义"""

    # 通用错误
    UNKNOWN_ERROR = ('UNKNOWN_ERROR', '未知错误')
    VALIDATION_ERROR = ('VALIDATION_ERROR', '数据验证失败')
    NOT_FOUND = ('NOT_FOUND', '资源不存在')
    PERMISSION_DENIED = ('PERMISSION_DENIED', '无权访问')
    BAD_REQUEST = ('BAD_REQUEST', '请求参数错误')

    # 业务错误
    PROJECT_NOT_FOUND = ('PROJECT_NOT_FOUND', '项目不存在')
    COLUMN_NOT_FOUND = ('COLUMN_NOT_FOUND', '列不存在')
    TASK_NOT_FOUND = ('TASK_NOT_FOUND', '任务不存在')
    USER_NOT_FOUND = ('USER_NOT_FOUND', '用户不存在')

    PROJECT_ACCESS_DENIED = ('PROJECT_ACCESS_DENIED', '无权访问此项目')
    TASK_ACCESS_DENIED = ('TASK_ACCESS_DENIED', '无权操作此任务')

    DATA_GENERATION_LIMIT = ('DATA_GENERATION_LIMIT', '数据生成数量超限')
    INTERNAL_ERROR = ('INTERNAL_ERROR', '服务器内部错误')


def error_response(code, message=None, status_code=None, details=None):
    """
    生成统一格式的错误响应

    Args:
        code: 错误码字符串
        message: 错误消息（可选，默认使用预设消息）
        status_code: HTTP 状态码（可选，默认根据错误类型推断）
        details: 额外详情数据（可选）

    Returns:
        Response: DRF Response 对象
    """
    # 预设的错误消息映射
    error_messages = dict(APIError.__dict__)

    # 确定状态码
    status_map = {
        'VALIDATION_ERROR': status.HTTP_400_BAD_REQUEST,
        'BAD_REQUEST': status.HTTP_400_BAD_REQUEST,
        'NOT_FOUND': status.HTTP_404_NOT_FOUND,
        'PROJECT_NOT_FOUND': status.HTTP_404_NOT_FOUND,
        'COLUMN_NOT_FOUND': status.HTTP_404_NOT_FOUND,
        'TASK_NOT_FOUND': status.HTTP_404_NOT_FOUND,
        'USER_NOT_FOUND': status.HTTP_404_NOT_FOUND,
        'PERMISSION_DENIED': status.HTTP_403_FORBIDDEN,
        'PROJECT_ACCESS_DENIED': status.HTTP_403_FORBIDDEN,
        'TASK_ACCESS_DENIED': status.HTTP_403_FORBIDDEN,
        'DATA_GENERATION_LIMIT': status.HTTP_400_BAD_REQUEST,
        'UNKNOWN_ERROR': status.HTTP_500_INTERNAL_SERVER_ERROR,
        'INTERNAL_ERROR': status.HTTP_500_INTERNAL_SERVER_ERROR,
    }

    http_status = status_code or status_map.get(code, status.HTTP_400_BAD_REQUEST)

    # 确定错误消息
    if message is None:
        message = error_messages.get(code, ('UNKNOWN_ERROR', '未知错误'))[1]

    response_data = {
        'error': True,
        'code': code,
        'message': message,
    }

    if details:
        response_data['details'] = details

    return Response(response_data, status=http_status)


def validation_error(errors):
    """
    生成数据验证失败的错误响应

    Args:
        errors: 验证错误字典

    Returns:
        Response: DRF Response 对象
    """
    return error_response(
        code='VALIDATION_ERROR',
        message='数据验证失败',
        details=errors
    )


def not_found(resource='资源'):
    """
    生成资源不存在的错误响应

    Args:
        resource: 资源类型描述

    Returns:
        Response: DRF Response 对象
    """
    return error_response(
        code='NOT_FOUND',
        message=f'{resource}不存在'
    )


def permission_denied(message='无权访问'):
    """
    生成权限拒绝的错误响应

    Args:
        message: 错误消息

    Returns:
        Response: DRF Response 对象
    """
    return error_response(
        code='PERMISSION_DENIED',
        message=message,
        status_code=status.HTTP_403_FORBIDDEN
    )


def bad_request(message='请求参数错误'):
    """
    生成请求参数错误的错误响应

    Args:
        message: 错误消息

    Returns:
        Response: DRF Response 对象
    """
    return error_response(
        code='BAD_REQUEST',
        message=message
    )


def internal_error(message='服务器内部错误'):
    """
    生成内部服务器错误的响应

    Args:
        message: 错误消息

    Returns:
        Response: DRF Response 对象
    """
    return error_response(
        code='INTERNAL_ERROR',
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )