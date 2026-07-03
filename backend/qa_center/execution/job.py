"""
TestJob — 一次压力测试任务的不可变描述。

所有执行路径（Case、DevOps、QuickTest）统一通过 TestJob 封装参数，
交由 ExecutionEngine.submit() 执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from room.models import Project
    from qa_center.models import PerformanceTestCase


@dataclass(frozen=True)
class TestJob:
    """一次压测任务的全部参数，不可变。

    通过工厂方法 ``TestJob.from_test_case()`` 快速构造。
    """

    test_case: 'PerformanceTestCase'
    host: str
    users: int = 10
    spawn_rate: int = 1
    run_time: str = "60s"
    async_mode: bool = True
    execution_id: Optional[int] = None
    project: Optional['Project'] = None
    user: Optional['User'] = None
    source: str = 'single'
    task_id: str = ''

    # ── 工厂方法 ──────────────────────────────────────────────────────

    @staticmethod
    def from_test_case(test_case: 'PerformanceTestCase', **overrides) -> 'TestJob':
        """从 PerformanceTestCase 提取默认值，可通过关键字参数覆盖。

        自动计算 host（从 test_case.url 解析 scheme+netloc）、
        users、spawn_rate、run_time。
        """
        parsed = urlparse(test_case.url)
        host = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else test_case.url

        defaults: Dict[str, Any] = {
            'test_case': test_case,
            'host': host,
            'users': test_case.concurrent_users,
            'spawn_rate': max(1, test_case.concurrent_users // 10),
            'run_time': f"{test_case.duration_seconds}s",
        }
        defaults.update(overrides)
        return TestJob(**defaults)

    # ── 便捷属性 ──────────────────────────────────────────────────────

    @property
    def case_id(self) -> int:
        return self.test_case.id

    @property
    def project_id(self) -> Optional[int]:
        if self.project is not None:
            return self.project.id
        return getattr(self.test_case, 'project_id', None)

    @property
    def user_id(self) -> Optional[int]:
        if self.user is not None:
            return self.user.id
        return None

    @property
    def expected_error_rate(self) -> float:
        return float(getattr(self.test_case, 'expected_error_rate', 5.0) or 5.0)


@dataclass
class ExecutionResult:
    """同步执行完成后的结果载体。"""

    ok: bool
    status: str  # 'passed' | 'failed' | 'error'
    execution_id: int
    stats: Dict[str, Any] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)
    test_result_id: int = 0
    perf_result_id: Optional[int] = None
    error: Optional[str] = None
    stopped_by_user: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ok': self.ok,
            'status': self.status,
            'execution_id': self.execution_id,
            'stats': self.stats,
            'payload': self.payload,
            'test_result_id': self.test_result_id,
            'perf_result_id': self.perf_result_id,
            'error': self.error,
            'stopped_by_user': self.stopped_by_user,
        }
