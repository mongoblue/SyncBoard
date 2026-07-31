"""UI 测试执行内核：环境变量渲染 + 统一执行入口。

同步 run / 异步 run_async / 批量 / DevOps 共用本模块，避免多处分叉。
变量语法与 API 测试一致：{{var_name}} / {{base_url}}。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from . import template_engine as te

logger = logging.getLogger("qa_center.runner")

# 步骤中参与模板渲染的字符串字段
_STEP_RENDER_FIELDS = (
    "url",
    "selector",
    "value",
    "expected_value",
    "attribute",
    "target_selector",
)

# 保存时允许的 action 白名单（含别名）
UI_STEP_ACTIONS = frozenset({
    "goto",
    "wait",
    "click",
    "click_if_visible",
    "dblclick",
    "double_click",
    "right_click",
    "context_click",
    "hover",
    "fill",
    "select",
    "upload",
    "keydown",
    "scroll",
    "drag",
    "drag_and_drop",
    "iframe_switch",
    "alert_handle",
    "screenshot",
    "assert_visible",
    "assert_text",
    "assert_contains_text",
    "assert_attribute",
    "assert_url",
    "assert_count",
    "assert_exists",
})


class UiConcurrencyLimitError(Exception):
    """并发 UI runner 已达上限。"""

    def __init__(self, message: str, *, max_concurrent: int):
        super().__init__(message)
        self.max_concurrent = max_concurrent


def validate_ui_steps(steps: Any) -> List[str]:
    """校验 steps 结构，返回错误列表（空表示通过）。"""
    errors: List[str] = []
    if steps is None:
        return errors
    if not isinstance(steps, list):
        return ["steps 必须是数组"]
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"steps[{i}] 必须是对象")
            continue
        action = step.get("action")
        if not action or not isinstance(action, str) or not action.strip():
            errors.append(f"steps[{i}].action 必填")
            continue
        action_key = action.strip().lower()
        if action_key not in UI_STEP_ACTIONS:
            errors.append(f"steps[{i}].action 不支持: {action}")
    return errors


def resolve_ui_environment(project, *, case=None, environment_id: Optional[int] = None):
    """请求覆盖 > 用例绑定 > 项目默认环境。"""
    if environment_id is not None:
        env = te.resolve_project_environment(project, env_id=environment_id)
        if env is not None:
            return env
    case_env_id = getattr(case, "environment_id", None) if case is not None else None
    if case_env_id:
        env = te.resolve_project_environment(project, env_id=case_env_id)
        if env is not None:
            return env
    return te.resolve_project_environment(project, env_id=None)


def build_ui_variable_pool(
    project,
    *,
    environment=None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    globals_ = te.load_project_globals(project)
    return te.build_variable_pool(
        environment=environment,
        global_vars=globals_,
        overrides=overrides,
    )


def _secret_keys(project) -> set[str]:
    try:
        from .models import TestGlobalVar
        return set(
            TestGlobalVar.objects.filter(project=project, is_secret=True).values_list("key", flat=True)
        )
    except Exception:
        logger.exception("读取 secret 全局变量失败")
        return set()


def mask_secret_variables(variables: Mapping[str, Any], project) -> Dict[str, Any]:
    secrets = _secret_keys(project)
    out: Dict[str, Any] = {}
    for k, v in (variables or {}).items():
        if k in secrets:
            out[str(k)] = "***"
        else:
            out[str(k)] = v
    return out


def render_ui_case_data(
    url: str,
    steps: Optional[List[dict]],
    variables: Mapping[str, Any],
) -> Tuple[str, List[dict], List[str]]:
    """渲染起始 URL 与步骤字段，返回 (url, steps, unresolved_var_names)。"""
    rendered_url = te.resolve_url(url or "", variables)
    unresolved: List[str] = []
    for name in te.find_unresolved(rendered_url):
        if name not in unresolved:
            unresolved.append(name)

    rendered_steps: List[dict] = []
    for raw in steps or []:
        if not isinstance(raw, dict):
            continue
        step = dict(raw)
        for field in _STEP_RENDER_FIELDS:
            if field not in step:
                continue
            val = step[field]
            if isinstance(val, str):
                new_val = te.render_string(val, variables)
                step[field] = new_val
                for name in te.find_unresolved(new_val):
                    if name not in unresolved:
                        unresolved.append(name)
            else:
                step[field] = te.render_value(val, variables)
        rendered_steps.append(step)
    return rendered_url, rendered_steps, unresolved


def prepare_ui_case_payload(
    project,
    *,
    url: str,
    steps: Optional[List[dict]] = None,
    case_id: Optional[int] = None,
    case=None,
    environment_id: Optional[int] = None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Tuple[dict, dict]:
    """准备 worker 输入与环境元数据。

    返回:
      case_data: 传给 runner_worker 的 dict
      env_meta: 写入 TestResult.test_params 的环境信息
    """
    environment = resolve_ui_environment(
        project, case=case, environment_id=environment_id
    )
    variables = build_ui_variable_pool(
        project, environment=environment, overrides=overrides
    )
    rendered_url, rendered_steps, unresolved = render_ui_case_data(url, steps, variables)
    case_data = {
        "case_id": case_id if case_id is not None else getattr(case, "id", None),
        "url": rendered_url,
        "steps": rendered_steps,
    }
    env_meta = {
        "environment_id": getattr(environment, "id", None),
        "environment_name": getattr(environment, "name", "") or "",
        "base_url": getattr(environment, "base_url", "") or variables.get("base_url", ""),
        "unresolved_variables": unresolved,
        "variables_preview": mask_secret_variables(variables, project),
        "original_url": url or "",
    }
    return case_data, env_meta


def prepare_and_execute_ui_case(
    project,
    *,
    url: str,
    steps: Optional[List[dict]] = None,
    case_id: Optional[int] = None,
    case=None,
    environment_id: Optional[int] = None,
    overrides: Optional[Mapping[str, Any]] = None,
    on_event: Optional[Callable[[dict], None]] = None,
    timeout_seconds: int = 300,
    task_id: Optional[str] = None,
) -> Tuple[dict, dict, dict]:
    """统一执行入口：渲染 → 子进程执行。

    返回 (final_result, env_meta, case_data)。
    """
    from .workers.runner_supervisor import execute_ui_case

    case_data, env_meta = prepare_ui_case_payload(
        project,
        url=url,
        steps=steps,
        case_id=case_id,
        case=case,
        environment_id=environment_id,
        overrides=overrides,
    )

    def _noop(_ev: dict) -> None:
        return None

    result = execute_ui_case(
        case_data,
        on_event=on_event or _noop,
        timeout_seconds=timeout_seconds,
        task_id=task_id,
    )
    return result, env_meta, case_data
