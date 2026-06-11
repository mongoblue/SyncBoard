"""新增 TestRunPlan 批量执行计划模型，并给 ApiAutoTestCase 加 timeout_seconds 字段。"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qa_center', '0010_apitestcase_related_tasks_and_more'),
        ('room', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautotestcase',
            name='timeout_seconds',
            field=models.IntegerField(default=30, verbose_name='请求超时(秒)'),
        ),
        migrations.CreateModel(
            name='TestRunPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='计划名称')),
                ('description', models.TextField(blank=True, verbose_name='描述')),
                ('case_ids', models.JSONField(default=list, verbose_name='用例ID列表')),
                ('parallel', models.BooleanField(default=False, verbose_name='并发执行')),
                ('max_workers', models.IntegerField(default=4, verbose_name='最大并发数')),
                ('stop_on_failure', models.BooleanField(default=False, verbose_name='遇错中止')),
                ('case_timeout_seconds', models.IntegerField(default=30, verbose_name='单用例超时(秒)')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_run_plans',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='创建者',
                )),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='test_run_plans',
                    to='room.project',
                    verbose_name='所属项目',
                )),
            ],
            options={
                'verbose_name': '批量执行计划',
                'verbose_name_plural': '批量执行计划',
                'db_table': 'qa_test_run_plans',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['project', '-created_at'], name='qa_test_run_project_c797d3_idx')],
            },
        ),
    ]
