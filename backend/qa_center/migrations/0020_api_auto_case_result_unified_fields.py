from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qa_center', '0019_testenvironment_allowlists'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='curl',
            field=models.JSONField(blank=True, default=dict, verbose_name='Curl快照'),
        ),
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='error_code',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='错误码'),
        ),
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='extracted_variables_preview',
            field=models.JSONField(blank=True, default=dict, verbose_name='提取变量预览'),
        ),
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='raw_status',
            field=models.CharField(blank=True, db_index=True, default='', max_length=32, verbose_name='原始状态'),
        ),
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='request_snapshot',
            field=models.JSONField(blank=True, default=dict, verbose_name='请求快照'),
        ),
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='response_snapshot',
            field=models.JSONField(blank=True, default=dict, verbose_name='响应快照'),
        ),
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='result_metadata',
            field=models.JSONField(blank=True, default=dict, verbose_name='结果元数据'),
        ),
        migrations.AddField(
            model_name='apiautotestcaseresult',
            name='trace_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='链路追踪ID'),
        ),
    ]
