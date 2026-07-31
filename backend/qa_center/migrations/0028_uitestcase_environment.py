# Generated manually for UI test production upgrade

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qa_center', '0027_add_perf_scenario_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='uitestcase',
            name='environment',
            field=models.ForeignKey(
                blank=True,
                help_text='用例级环境覆盖；为空时回退到项目默认环境',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ui_test_cases',
                to='qa_center.testenvironment',
                verbose_name='绑定环境',
            ),
        ),
    ]
