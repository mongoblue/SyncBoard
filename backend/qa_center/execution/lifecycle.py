"""
Run Lifecycle 状态机 —— 压力测试标准化生命周期。

状态列表（按时间序）:
    pending     → 已创建执行记录，等待执行器
    preparing   → 正在生成 locustfile / 校验参数
    probing     → 正在做目标 URL 连通性预检
    starting    → 正在启动 Locust 子进程
    ramping     → 正在增加虚拟用户（rps>0 但尚未稳定）
    running     → 已有请求产生，正在稳定压测
    collecting  → 压测结束，正在收集结果
    passed      → 通过
    failed      → 压测执行完成但断言未通过
    error       → 执行异常
    stopped     → 用户停止
    timeout     → 超过最大运行时间被强制终止

中间态（瞬时）:
    stopping    → 收到停止信号，正在终止子进程

用法:
    from qa_center.execution.lifecycle import Lifecycle, LifecycleState

    lc = Lifecycle()
    lc.transition(LifecycleState.PREPARING)
    lc.transition(LifecycleState.PROBING, reason='Target URL connectivity check')
    ...
    lc.transition(LifecycleState.ERROR, reason='probe_failed', error_message='Connection refused')
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional, Tuple


class LifecycleState(StrEnum):
    """压力测试生命周期状态枚举。"""

    PENDING = "pending"
    PREPARING = "preparing"
    PROBING = "probing"
    STARTING = "starting"
    RAMPING = "ramping"
    RUNNING = "running"
    COLLECTING = "collecting"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    STOPPED = "stopped"
    TIMEOUT = "timeout"

    # ── 中间态（瞬时） ──────────────────────────────────────────
    STOPPING = "stopping"


# ── 中文显示名 ──────────────────────────────────────────────────

LIFECYCLE_LABELS: Dict[LifecycleState, str] = {
    LifecycleState.PENDING: "等待执行",
    LifecycleState.PREPARING: "准备中",
    LifecycleState.PROBING: "连通性检查",
    LifecycleState.STARTING: "启动中",
    LifecycleState.RAMPING: "加压中",
    LifecycleState.RUNNING: "运行中",
    LifecycleState.COLLECTING: "收集中",
    LifecycleState.PASSED: "通过",
    LifecycleState.FAILED: "未通过",
    LifecycleState.ERROR: "异常",
    LifecycleState.STOPPED: "已停止",
    LifecycleState.TIMEOUT: "超时",
    LifecycleState.STOPPING: "正在停止",
}

# ── 合法状态转换 ───────────────────────────────────────────────
# key: 当前状态，value: 可转换到的状态集合

ALLOWED_TRANSITIONS: Dict[LifecycleState, Tuple[LifecycleState, ...]] = {
    LifecycleState.PENDING: (
        LifecycleState.PREPARING,
        LifecycleState.ERROR,       # 执行器不可用等
        LifecycleState.STOPPED,     # 用户在 pending 阶段取消
    ),
    LifecycleState.PREPARING: (
        LifecycleState.PROBING,
        LifecycleState.ERROR,       # locustfile 生成失败
    ),
    LifecycleState.PROBING: (
        LifecycleState.STARTING,
        LifecycleState.ERROR,       # probe_failed
    ),
    LifecycleState.STARTING: (
        LifecycleState.RAMPING,
        LifecycleState.RUNNING,     # 小并发可能跳过快增阶段
        LifecycleState.COLLECTING,  # 启动后立即结束且无请求
        LifecycleState.ERROR,       # locust_start_failed
    ),
    LifecycleState.RAMPING: (
        LifecycleState.RUNNING,
        LifecycleState.ERROR,
        LifecycleState.STOPPING,
        LifecycleState.TIMEOUT,
    ),
    LifecycleState.RUNNING: (
        LifecycleState.COLLECTING,
        LifecycleState.ERROR,
        LifecycleState.STOPPING,
        LifecycleState.TIMEOUT,
    ),
    LifecycleState.COLLECTING: (
        LifecycleState.PASSED,
        LifecycleState.FAILED,
        LifecycleState.ERROR,
    ),
    LifecycleState.STOPPING: (
        LifecycleState.STOPPED,
        LifecycleState.ERROR,       # kill 失败等极端情况
    ),
    # 终态：不再允许转换
    LifecycleState.PASSED: (),
    LifecycleState.FAILED: (),
    LifecycleState.ERROR: (),
    LifecycleState.STOPPED: (),
    LifecycleState.TIMEOUT: (),
}

# ── 活跃态（测试仍在进行中） ──────────────────────────────────

ACTIVE_STATES: Tuple[LifecycleState, ...] = (
    LifecycleState.PENDING,
    LifecycleState.PREPARING,
    LifecycleState.PROBING,
    LifecycleState.STARTING,
    LifecycleState.RAMPING,
    LifecycleState.RUNNING,
    LifecycleState.COLLECTING,
    LifecycleState.STOPPING,
)

# ── 终态 ────────────────────────────────────────────────────────

TERMINAL_STATES: Tuple[LifecycleState, ...] = (
    LifecycleState.PASSED,
    LifecycleState.FAILED,
    LifecycleState.ERROR,
    LifecycleState.STOPPED,
    LifecycleState.TIMEOUT,
)

# ── 尚未产生指标数据的阶段 ─────────────────────────────────────
# 前端在这些阶段不应显示 "0 metrics"

PRE_METRICS_STATES: Tuple[LifecycleState, ...] = (
    LifecycleState.PENDING,
    LifecycleState.PREPARING,
    LifecycleState.PROBING,
    LifecycleState.STARTING,
)


def is_active(state: LifecycleState) -> bool:
    """是否仍在执行中（非终态）。"""
    return state in ACTIVE_STATES


def is_terminal(state: LifecycleState) -> bool:
    """是否已进入终态。"""
    return state in TERMINAL_STATES


def is_pre_metrics(state: LifecycleState) -> bool:
    """是否处于尚未产生指标数据的阶段。"""
    return state in PRE_METRICS_STATES


def can_transition(from_state: LifecycleState, to_state: LifecycleState) -> bool:
    """检查状态转换是否合法。"""
    allowed = ALLOWED_TRANSITIONS.get(from_state, ())
    return to_state in allowed


@dataclass
class LifecycleSnapshot:
    """一次生命周期快照，用于 WS 推送和持久化。"""
    state: LifecycleState = LifecycleState.PENDING
    reason: str = ""
    entered_at: Optional[float] = None
    previous_state: Optional[LifecycleState] = None


@dataclass
class Lifecycle:
    """生命周期状态机。

    管理状态转换、记录状态进入时间和原因。
    不负责持久化（由 Engine 负责），不负责 WS 推送（由 Worker 负责）。

    用法::

        lc = Lifecycle(initial_state=LifecycleState.PENDING)
        lc.transition(LifecycleState.PREPARING)
        lc.transition(LifecycleState.ERROR, reason='probe_failed')
        assert lc.current == LifecycleState.ERROR
        assert lc.snapshot.reason == 'probe_failed'
    """

    current: LifecycleState = LifecycleState.PENDING
    history: List[LifecycleSnapshot] = field(default_factory=list)
    _lock_entered_at: Optional[float] = None

    def __post_init__(self):
        if not self.history:
            self.history.append(LifecycleSnapshot(
                state=self.current,
                entered_at=time.time(),
            ))

    @property
    def snapshot(self) -> LifecycleSnapshot:
        """当前状态快照。"""
        return self.history[-1] if self.history else LifecycleSnapshot()

    @property
    def previous_state(self) -> Optional[LifecycleState]:
        """前一个状态（用于回滚等场景）。"""
        if len(self.history) >= 2:
            return self.history[-2].state
        return None

    def transition(
        self,
        to_state: LifecycleState,
        reason: str = "",
        error_message: str = "",
    ) -> LifecycleSnapshot:
        """执行状态转换。

        Args:
            to_state: 目标状态
            reason: 转换原因（如 'probe_failed', 'locust_start_failed'）
            error_message: 错误详情（进入 error 状态时使用）

        Returns:
            新状态快照

        Raises:
            ValueError: 非法状态转换
        """
        if not can_transition(self.current, to_state):
            raise ValueError(
                f"非法状态转换: {self.current.value} → {to_state.value}。"
                f"允许的目标: {[s.value for s in ALLOWED_TRANSITIONS.get(self.current, ())]}"
            )

        prev = self.current
        self.current = to_state

        snapshot = LifecycleSnapshot(
            state=to_state,
            reason=reason,
            entered_at=time.time(),
            previous_state=prev,
        )
        self.history.append(snapshot)

        return snapshot

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict（用于 WS payload）。"""
        snap = self.snapshot
        return {
            'lifecycle_state': self.current.value,
            'lifecycle_reason': snap.reason,
            'lifecycle_entered_at': snap.entered_at,
            'lifecycle_previous_state': snap.previous_state.value if snap.previous_state else None,
            'lifecycle_label': LIFECYCLE_LABELS.get(self.current, self.current.value),
            'lifecycle_is_terminal': is_terminal(self.current),
            'lifecycle_is_active': is_active(self.current),
            'lifecycle_is_pre_metrics': is_pre_metrics(self.current),
            'lifecycle_history': [
                {
                    'state': h.state.value,
                    'label': LIFECYCLE_LABELS.get(h.state, h.state.value),
                    'reason': h.reason,
                    'entered_at': h.entered_at,
                    'previous_state': h.previous_state.value if h.previous_state else None,
                }
                for h in self.history
            ],
        }
