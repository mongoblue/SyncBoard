"""
Playwright 交互式录制器
用于捕获用户在浏览器中的操作并自动生成测试步骤
基于 Playwright Expert 最佳实践

[DEPRECATED] 此模块已被 recorder_supervisor + recorder_worker 子进程方案替代。
保留以兼容可能的回滚。下一个迭代删除。请勿新代码使用。
"""

import json
import logging
import os
import tempfile
import threading
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from django.conf import settings
from channels.layers import get_channel_layer

logger = logging.getLogger('django')
