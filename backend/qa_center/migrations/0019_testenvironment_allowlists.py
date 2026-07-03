from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qa_center', '0018_task8_pipeline_ci_integration'),
    ]

    operations = [
        migrations.AddField(
            model_name='testenvironment',
            name='allowed_cidrs',
            field=models.JSONField(blank=True, default=list, verbose_name='SSRF 允许网段'),
        ),
        migrations.AddField(
            model_name='testenvironment',
            name='allowed_hosts',
            field=models.JSONField(blank=True, default=list, verbose_name='SSRF 允许主机'),
        ),
    ]
