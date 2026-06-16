import os
import time
import shutil
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "清理 Playwright 临时目录（默认 24h 前）"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **opts):
        cutoff = time.time() - opts["hours"] * 3600
        base = os.path.join(settings.BASE_DIR, ".playwright-temp")
        if not os.path.exists(base):
            self.stdout.write("目录不存在")
            return
        removed = 0
        for name in os.listdir(base):
            full = os.path.join(base, name)
            if os.path.isdir(full) and os.path.getmtime(full) < cutoff:
                shutil.rmtree(full, ignore_errors=True)
                removed += 1
        self.stdout.write(f"已清理 {removed} 个目录")
