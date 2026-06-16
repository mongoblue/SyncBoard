from django.apps import AppConfig
import os
import time
import shutil
import logging


class QaCenterConfig(AppConfig):
    name = "qa_center"

    def ready(self):
        try:
            self._cleanup_playwright_temp()
        except Exception:
            logging.getLogger("qa_center.runner").exception("启动清理失败")

    def _cleanup_playwright_temp(self):
        from django.conf import settings
        base = os.path.join(settings.BASE_DIR, ".playwright-temp")
        if not os.path.exists(base):
            return
        cutoff = time.time() - 24 * 3600
        for name in os.listdir(base):
            full = os.path.join(base, name)
            try:
                if os.path.isdir(full) and os.path.getmtime(full) < cutoff:
                    shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass
