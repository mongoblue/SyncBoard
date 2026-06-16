"""
Playwright UI 测试运行器
用于执行 E2E 自动化测试

[DEPRECATED] 此模块已被 runner_supervisor + runner_worker 子进程方案替代。
保留以兼容可能的回滚。下一个迭代删除。请勿新代码使用。
"""

import base64
import json
import logging
import os
import tempfile
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from django.conf import settings

logger = logging.getLogger('django')
