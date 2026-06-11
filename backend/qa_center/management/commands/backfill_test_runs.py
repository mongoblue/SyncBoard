"""把老 TestResult.test_log(JSON) 里识别为批量的记录回填到 TestRun + TestRunCaseResult。

判定标准:summary.total > 1

注意:TestRun.created_at 为 auto_now_add=True,无法在 create() 时直接覆盖,
因此回填出来的 TestRun.created_at 会是当前时间;历史"执行时刻"则由
started_at/completed_at 保留(回退到 tr.created_at)。
"""
import json
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from qa_center.models import TestRun, TestRunCaseResult, TestResult

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '回填历史 TestResult 批量执行记录到 TestRun + TestRunCaseResult'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90, help='回填最近 N 天')
        parser.add_argument('--batch', type=int, default=100, help='每次处理多少条')
        parser.add_argument('--dry-run', action='store_true', help='只看预估,不写库')

    def handle(self, *args, **options):
        days = options['days']
        batch = options['batch']
        dry_run = options['dry_run']

        cutoff = timezone.now() - timedelta(days=days)
        qs = TestResult.objects.filter(
            test_type='api', created_at__gte=cutoff,
        ).exclude(test_log='').order_by('-created_at')

        total = qs.count()
        self.stdout.write(f'候选 {total} 条 TestResult(近 {days} 天)')

        if dry_run:
            # 估算有多少会被识别为批量
            estimate = 0
            for tr in qs.iterator():
                log = self._parse_log(tr.test_log)
                if log and log.get('summary', {}).get('total', 0) > 1:
                    estimate += 1
            self.stdout.write(self.style.WARNING(
                f'[DRY-RUN] 预计回填 {estimate} 条批量记录, --batch={batch}'
            ))
            return

        processed = 0
        created_runs = 0
        for tr in qs.iterator():
            processed += 1
            log = self._parse_log(tr.test_log)
            if not log:
                continue
            summary = log.get('summary', {})
            total_count = summary.get('total', 0)
            if total_count <= 1:
                continue
            results = log.get('results', [])
            if not results:
                continue

            # 跳过已回填
            if TestRun.objects.filter(name=tr.name, project=tr.project,
                                       created_at__date=tr.created_at.date()).exists():
                continue

            run = TestRun.objects.create(
                project=tr.project,
                name=tr.name,
                trigger='manual',
                test_type='api',
                status='passed' if tr.status == 'passed' else 'failed',
                total_count=total_count,
                passed_count=summary.get('passed', 0),
                failed_count=summary.get('failed', 0),
                error_count=summary.get('error', 0) if 'error' in summary else 0,
                pass_rate=summary.get('pass_rate', 0),
                duration_ms=tr.duration_ms,
                started_at=tr.started_at or tr.created_at,
                completed_at=tr.completed_at or tr.created_at,
                triggered_by=tr.executed_by,
                config_snapshot={'source': 'backfill', 'legacy_test_result_id': tr.id},
            )
            created_runs += 1

            for idx, item in enumerate(results, 1):
                TestRunCaseResult.objects.create(
                    test_run=run,
                    case_type='api',
                    sequence=idx,
                    api_test_case_id=item.get('case_id') or tr.api_test_case_id,
                    status='passed' if item.get('passed') else 'failed',
                    duration_ms=item.get('response_time_ms'),
                    status_code=item.get('response', {}).get('status_code'),
                    response_body=str(item.get('response', {}).get('body', ''))[:10000],
                    response_headers=item.get('response', {}).get('headers', {}),
                    assertion_results=item.get('assertions', []),
                    request_snapshot=item.get('request', {}),
                    curl='',
                    legacy_test_result_id=tr.id,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                )

            if processed % batch == 0:
                self.stdout.write(f'已处理 {processed}/{total}...')

        self.stdout.write(self.style.SUCCESS(
            f'回填完成: 扫描 {processed} 条, 新建 {created_runs} 个 TestRun'
        ))

    @staticmethod
    def _parse_log(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
