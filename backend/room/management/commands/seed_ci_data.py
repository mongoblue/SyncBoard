from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from room.models import Project, Column

class Command(BaseCommand):
    help = '自动生成 CI/E2E 测试所需的基础数据'

    def handle(self, *args, **options):
        self.stdout.write('🌱 开始准备测试数据...')

        # 1. 创建/获取用户
        if not User.objects.filter(username='mongoblue').exists():
            user = User.objects.create_user('mongoblue', 'test@example.com', '13579mnb')
            self.stdout.write(self.style.SUCCESS('✅ 用户 mongoblue 创建成功'))
        else:
            user = User.objects.get(username='mongoblue')
            self.stdout.write('ℹ️ 用户 mongoblue 已存在')

        # 2. 创建一个测试项目
        if not Project.objects.filter(name='CI Automantion Project').exists():
            project = Project.objects.create(name='CI Automantion Project', owner=user)
            self.stdout.write(self.style.SUCCESS(f'✅ 项目 {project.name} 创建成功'))
        else:
            project = Project.objects.filter(name='CI Automantion Project').first()
            self.stdout.write(f'ℹ️ 项目 {project.name} 已存在')

        # 3. 确保有 'To Do' 列
        col, created = Column.objects.get_or_create(
            project=project, 
            title='To Do', 
            defaults={'position': 1}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✅ To Do 列创建成功'))
        else:
            self.stdout.write('ℹ️ To Do 列已存在')

        self.stdout.write(self.style.SUCCESS('✨ 所有测试数据准备就绪！'))
