"""模板渲染 —— M3.2。

支持 ``{{var_name}}`` 占位符，按以下优先级查找变量值：

  1. 临时上下文 ``overrides``（比如 extractor 提取出的运行时变量，M3.3 再用）
  2. ``TestEnvironment.variables``
  3. ``TestGlobalVar`` 项目级全局变量
  4. ``TestEnvironment.base_url`` 暴露为 ``{{base_url}}`` 这个特殊键

变量名匹配规则（与 Postman / Apifox 对齐）：
  - 大小写敏感
  - 允许 ``[A-Za-z0-9_]``，前后允许空白：``{{  user_id  }}``
  - 未找到的变量保持原样（``{{missing}}``），调用方可以决定是否报错

设计目标：
  - 渲染失败不应该让整次测试崩——找不到变量就保留原样
  - 字典 / 列表 / 字符串都能渲染（headers 和 body 都会经过）
  - 数字/bool 类型保持类型，不强转 str
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Optional


_PLACEHOLDER_RE = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}')


def build_variable_pool(
    *,
    environment=None,
    global_vars: Optional[Iterable] = None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """合并出最终的变量字典。

    参数：
      environment: TestEnvironment 实例或 None
      global_vars: TestGlobalVar 查询集 / 列表
      overrides: 运行时附加变量（最高优先级），如 extractor 抓出来的字段
    """
    pool: Dict[str, Any] = {}

    # 全局变量（最低优先级）
    if global_vars:
        for gv in global_vars:
            key = getattr(gv, 'key', None)
            if key:
                pool[key] = getattr(gv, 'value', '')

    # 环境变量
    if environment is not None:
        env_vars = getattr(environment, 'variables', None) or {}
        if isinstance(env_vars, dict):
            for k, v in env_vars.items():
                pool[str(k)] = v
        base = getattr(environment, 'base_url', None)
        if base and 'base_url' not in pool:
            pool['base_url'] = base

    # overrides（最高优先级）
    if overrides:
        for k, v in overrides.items():
            pool[str(k)] = v

    return pool


def render_string(text: str, variables: Mapping[str, Any]) -> str:
    """对单个字符串做 ``{{var}}`` 替换。未匹配的占位符保持原样。"""
    if not text or '{{' not in text:
        return text

    def _sub(m: re.Match) -> str:
        name = m.group(1)
        if name in variables:
            v = variables[name]
            return '' if v is None else str(v)
        return m.group(0)  # 保留原样，方便定位漏配

    return _PLACEHOLDER_RE.sub(_sub, text)


def render_value(value: Any, variables: Mapping[str, Any]) -> Any:
    """对任意 JSON 兼容值做深度渲染。

    str -> 替换
    dict -> key/value 都递归
    list/tuple -> 元素递归
    其它原样返回
    """
    if isinstance(value, str):
        return render_string(value, variables)
    if isinstance(value, dict):
        return {render_value(k, variables): render_value(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(v, variables) for v in value]
    if isinstance(value, tuple):
        return tuple(render_value(v, variables) for v in value)
    return value


def resolve_url(url: str, variables: Mapping[str, Any]) -> str:
    """渲染 URL，并对相对路径自动拼接 ``base_url``。

    - 完整 URL（含 scheme） → 仅做变量替换
    - ``/api/foo`` 这种相对 URL → 拼接 ``{{base_url}}`` 当作前缀
    - 没有 base_url 时不拼接，原样返回
    """
    rendered = render_string(url or '', variables)
    if not rendered:
        return rendered
    low = rendered.lower()
    if low.startswith(('http://', 'https://', 'ws://', 'wss://')):
        return rendered
    base = variables.get('base_url')
    if not base:
        return rendered
    base = str(base).rstrip('/')
    if rendered.startswith('/'):
        return f'{base}{rendered}'
    return f'{base}/{rendered}'


def find_unresolved(text: str) -> list:
    """返回字符串里仍未被替换的 ``{{var}}`` 名字列表（去重保序）。"""
    if not text or '{{' not in text:
        return []
    seen: list = []
    for name in _PLACEHOLDER_RE.findall(text):
        if name not in seen:
            seen.append(name)
    return seen


def resolve_project_environment(project, env_id: Optional[int] = None):
    """按 env_id 取环境；为空则取项目 is_default=True 的那条；都没有返回 None。

    保持模型解耦：在这里 import，避免循环引用。
    """
    from .models import TestEnvironment
    qs = TestEnvironment.objects.filter(project=project)
    if env_id:
        return qs.filter(id=env_id).first()
    return qs.filter(is_default=True).first() or qs.first()


def load_project_globals(project):
    """读项目级全局变量（无缓存，调用方自行决定缓存策略）。"""
    from .models import TestGlobalVar
    return list(TestGlobalVar.objects.filter(project=project))
