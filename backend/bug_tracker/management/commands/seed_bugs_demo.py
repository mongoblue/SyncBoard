"""为指定项目种入 Bug 演示数据（幂等）"""
from django.core.management.base import BaseCommand
from room.models import Project
from bug_tracker.seed import seed_demo_bugs


class Command(BaseCommand):
    help = '为项目种入 8 条 [DEMO] 前缀的 Bug（幂等）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--project', dest='project_id', default=None,
            help='项目 ID（不传则取名为 "CI Automantion Project" 的项目）',
        )

    def handle(self, *args, **options):
        project_id = options.get('project_id')
        if project_id:
            project = Project.objects.filter(pk=project_id).first()
        else:
            project = Project.objects.filter(name='CI Automantion Project').first()

        if not project:
            self.stdout.write(self.style.WARNING('未找到目标项目，跳过'))
            return

        added = seed_demo_bugs(project)
        if added:
            self.stdout.write(self.style.SUCCESS(f'✅ 已生成 {added} 条示例 Bug'))
        else:
            self.stdout.write('ℹ️ 示例 Bug 已存在，跳过')
