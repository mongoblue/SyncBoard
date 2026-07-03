"""
统一执行引擎 — 压力测试唯一入口。

三层架构：
    ExecutionEngine  — 编排层：创建 Job、调度 Worker、持久化结果
    ExecutionWorker  — 执行层：管理单次测试生命周期（start/poll/stop/collect）
    LocustRunner     — 适配层：Locust 子进程管理（仅为 Worker 内部实现）

对外暴露：
    TestJob          — 不可变的任务描述
    ExecutionResult  — 同步执行结果
    ExecutionEngine  — 统一执行入口
    ExecutionWorker  — 单次测试生命周期管理器
"""

from .job import TestJob, ExecutionResult
from .engine import ExecutionEngine
from .worker import ExecutionWorker

__all__ = ['TestJob', 'ExecutionResult', 'ExecutionEngine', 'ExecutionWorker']
