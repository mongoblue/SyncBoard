"""
清理过期的性能测试产物目录。

用法:
    python manage.py cleanup_perf_artifacts
    python manage.py cleanup_perf_artifacts --dry-run
    python manage.py cleanup_perf_artifacts --days 14
"""

import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand

from qa_center.models import TestResult
from qa_center.locust_runner import _get_artifact_base_dir

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '清理过期的压力测试产物目录'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅显示将要删除的目录，不实际删除',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help=f'保留天数（默认: {getattr(settings, "PERF_ARTIFACT_RETENTION_DAYS", 7)}）',
        )
        parser.add_argument(
            '--keep-failed',
            action='store_true',
            default=None,
            help='保留失败运行的产物',
        )

    def handle(self, **options):
        dry_run = options['dry_run']
        retention_days = options['days'] or getattr(
            settings, 'PERF_ARTIFACT_RETENTION_DAYS', 7
        )
        keep_failed = (
            options['keep_failed']
            if options['keep_failed'] is not None
            else getattr(settings, 'PERF_KEEP_FAILED_ARTIFACTS', True)
        )

        base_dir = _get_artifact_base_dir()
        if not os.path.isdir(base_dir):
            self.stdout.write(f'产物目录不存在: {base_dir}')
            return

        cutoff = time.time() - (retention_days * 86400)
        now_utc = datetime.now(timezone.utc)

        # ── 收集失败运行的 execution_id ────────────────────────
        failed_ids: set = set()
        if keep_failed:
            # 最近 90 天内的失败记录
            since = now_utc - timedelta(days=90)
            failed_qs = TestResult.objects.filter(
                test_type='performance',
                status__in=('error', 'failed'),
                completed_at__gte=since,
            ).values_list('id', flat=True)
            failed_ids = set(str(x) for x in failed_qs)

        deleted = 0
        kept = 0
        total_size = 0

        for entry in sorted(os.listdir(base_dir)):
            entry_path = os.path.join(base_dir, entry)
            if not os.path.isdir(entry_path):
                continue

            # ── 保留失败运行 ──────────────────────────────────
            if keep_failed and entry in failed_ids:
                kept += 1
                continue

            # ── 检查目录修改时间 ──────────────────────────────
            try:
                mtime = os.path.getmtime(entry_path)
            except OSError:
                mtime = 0

            if mtime > cutoff:
                kept += 1
                continue

            # ── 删除 ──────────────────────────────────────────
            dir_size = _get_dir_size(entry_path)
            total_size += dir_size

            if dry_run:
                self.stdout.write(
                    f'[DRY RUN] 将删除: {entry} ({_format_size(dir_size)})'
                )
            else:
                try:
                    shutil.rmtree(entry_path)
                    self.stdout.write(f'已删除: {entry} ({_format_size(dir_size)})')
                except OSError as exc:
                    self.stderr.write(f'删除失败: {entry} — {exc}')
                    continue

            deleted += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'清理完成: 删除 {deleted} 个目录 ({_format_size(total_size)}), '
                f'保留 {kept} 个（{dry_run and "DRY RUN" or "实际执行"}）'
            )
        )


def _get_dir_size(path: str) -> int:
    """递归计算目录大小。"""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _format_size(size: int) -> str:
    """格式化字节为可读字符串。"""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'
