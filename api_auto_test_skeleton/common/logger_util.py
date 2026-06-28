"""
Logger Util - 日志工具
支持输出到控制台和文件
提供不同级别的日志记录
"""
import os
import sys
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler


class LoggerUtil:
    """日志工具类"""

    _loggers = {}

    def __init__(
        self,
        name: str = "api_test",
        log_dir: str = "logs",
        log_file: Optional[str] = None,
        level: int = logging.INFO,
        console: bool = True,
        file_handler: bool = True,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5
    ):
        """
        初始化日志工具

        Args:
            name: 日志记录器名称
            log_dir: 日志文件目录
            log_file: 日志文件名，默认为 {name}_{日期}.log
            level: 日志级别，默认为 INFO
            console: 是否输出到控制台，默认为 True
            file_handler: 是否输出到文件，默认为 True
            max_bytes: 单个日志文件最大字节数，默认为 10MB
            backup_count: 保留的备份文件数量，默认为 5
        """
        self.name = name
        self.log_dir = log_dir
        self.log_file = log_file or f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        self.level = level
        self.console = console
        self.file_handler_enabled = file_handler
        self.max_bytes = max_bytes
        self.backup_count = backup_count

        self.logger = self._get_logger()

    def _get_logger(self) -> logging.Logger:
        """获取或创建日志记录器"""
        if self.name in LoggerUtil._loggers:
            return LoggerUtil._loggers[self.name]

        logger = logging.getLogger(self.name)
        logger.setLevel(self.level)
        logger.propagate = False

        if logger.handlers:
            logger.handlers.clear()

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        if self.console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        if self.file_handler_enabled:
            log_path = Path(self.log_dir)
            log_path.mkdir(parents=True, exist_ok=True)

            file_path = log_path / self.log_file

            file_handler = RotatingFileHandler(
                filename=str(file_path),
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        LoggerUtil._loggers[self.name] = logger
        return logger

    def debug(self, message: str, *args, **kwargs):
        """记录 DEBUG 级别日志"""
        self.logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """记录 INFO 级别日志"""
        self.logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """记录 WARNING 级别日志"""
        self.logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """记录 ERROR 级别日志"""
        self.logger.error(message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        """记录 CRITICAL 级别日志"""
        self.logger.critical(message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs):
        """记录异常日志（自动包含堆栈信息）"""
        self.logger.exception(message, *args, **kwargs)

    def log_request(self, method: str, url: str, **kwargs):
        """记录 HTTP 请求"""
        self.info(f"📤 REQUEST | {method} | {url}")
        if kwargs.get("headers"):
            self.debug(f"   Headers: {kwargs['headers']}")
        if kwargs.get("params"):
            self.debug(f"   Params: {kwargs['params']}")
        if kwargs.get("json"):
            import json
            self.debug(f"   Body: {json.dumps(kwargs['json'], ensure_ascii=False)}")

    def log_response(self, response, elapsed_ms: float):
        """记录 HTTP 响应"""
        import json
        status = response.status_code
        reason = response.reason

        if 200 <= status < 300:
            level = self.info
            icon = "✅"
        elif 300 <= status < 400:
            level = self.warning
            icon = "🔄"
        else:
            level = self.error
            icon = "❌"

        level(f"📥 RESPONSE | {icon} {status} {reason} | {elapsed_ms:.0f}ms")

        try:
            body = response.json()
            body_str = json.dumps(body, ensure_ascii=False)
            if len(body_str) > 500:
                body_str = body_str[:500] + "..."
            self.debug(f"   Body: {body_str}")
        except Exception:
            if response.text:
                text = response.text[:500]
                self.debug(f"   Body: {text}")

    def section(self, title: str):
        """输出分段标题"""
        separator = "=" * 60
        self.info(f"\n{separator}")
        self.info(f"  {title}")
        self.info(f"{separator}")

    @staticmethod
    def get_logger(
        name: str = "api_test",
        log_dir: str = "logs",
        **kwargs
    ) -> "LoggerUtil":
        """
        静态方法：获取日志工具实例

        Args:
            name: 日志记录器名称
            log_dir: 日志文件目录
            **kwargs: 其他初始化参数

        Returns:
            LoggerUtil 实例
        """
        return LoggerUtil(name=name, log_dir=log_dir, **kwargs)


class TestLogger:
    """测试日志装饰器 - 用于标记测试开始/结束"""

    def __init__(self, logger: LoggerUtil, test_name: str):
        self.logger = logger
        self.test_name = test_name

    def __enter__(self):
        self.logger.section(f"🧪 {self.test_name}")
        self.logger.info(f"开始执行...")
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.time() - self.start_time) * 1000

        if exc_type is None:
            self.logger.info(f"✅ 测试通过 | 耗时: {elapsed:.0f}ms")
        else:
            self.logger.error(f"❌ 测试失败 | 耗时: {elapsed:.0f}ms")
            self.logger.error(f"   异常: {exc_type.__name__}: {exc_val}")

        self.logger.info("=" * 60 + "\n")


if __name__ == "__main__":
    print("=" * 60)
    print("LoggerUtil 使用示例")
    print("=" * 60)

    logger = LoggerUtil.get_logger(
        name="demo",
        log_dir="logs",
        level=logging.DEBUG
    )

    logger.info("这是一条 info 日志")
    logger.debug("这是一条 debug 日志")
    logger.warning("这是一条 warning 日志")
    logger.error("这是一条 error 日志")

    logger.section("HTTP 请求日志示例")

    import requests
    session = requests.Session()

    logger.log_request("GET", "http://httpbin.org/get", params={"key": "value"})
    response = session.get("http://httpbin.org/get", timeout=10)
    logger.log_response(response, 100)

    logger.log_request("POST", "http://httpbin.org/post", json={"username": "admin"})
    response = session.post("http://httpbin.org/post", json={"username": "admin"}, timeout=10)
    logger.log_response(response, 150)

    with TestLogger(logger, "登录功能测试") as tl:
        logger.info("执行登录检查...")
        assert True

    print("\n日志已输出到 logs/demo_*.log")
