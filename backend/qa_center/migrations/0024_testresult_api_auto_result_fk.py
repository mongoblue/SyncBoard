"""0024 为 TestResult 加 api_auto_result FK 指针。

P1.5：API 自动化执行（单条/suite/run_plan）落库 ApiAutoTestResult 时，
同步镜像一条 TestResult，让"测试结果中心"统一查询 TestResult 即可看到所有类型结果。
本迁移只加 FK 列，不动数据；存量回填由 0025 完成。
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('qa_center', '0023_fix_project_fk_uuid'),
    ]
    operations = [
        migrations.AddField(
            model_name='testresult',
            name='api_auto_result',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name='mirrored_test_results',
                to='qa_center.apiautotestresult',
                verbose_name='关联API自动化结果',
                help_text='API 自动化执行镜像指针；非空时点击列表行应跳转 AutoResultDetail',
            ),
        ),
    ]
