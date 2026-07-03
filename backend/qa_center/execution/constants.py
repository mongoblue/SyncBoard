"""
压力测试模块共享常量。

避免 locust_runner ↔ execution 之间的循环导入。
"""

# ── Runner 状态 ──────────────────────────────────────────────

LOCUST_NOT_STARTED = 'locust_not_started'
METRICS_NOT_CREATED = 'metrics_file_not_created'
METRICS_EMPTY = 'metrics_file_empty'
METRICS_PARSE_ERROR = 'metrics_file_parse_error'
LOCUST_PROCESS_EXITED = 'locust_process_exited'
LOCUST_RUNNING_NO_REQUESTS = 'locust_running_no_requests'
LOCUST_RUNNING_WITH_REQUESTS = 'locust_running_with_requests'

# ── 超时配置 ──────────────────────────────────────────────────

METRICS_FILE_CREATION_TIMEOUT = 3.0  # 指标文件创建最大等待秒数
