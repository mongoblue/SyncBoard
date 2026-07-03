from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qa_center', '0020_api_auto_case_result_unified_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='apitestresult',
            name='curl',
            field=models.JSONField(blank=True, default=dict, verbose_name='Curl快照'),
        ),
        migrations.AddField(
            model_name='apitestresult',
            name='error_code',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='错误码'),
        ),
        migrations.AddField(
            model_name='apitestresult',
            name='extracted_variables_preview',
            field=models.JSONField(blank=True, default=dict, verbose_name='提取变量预览'),
        ),
        migrations.AddField(
            model_name='apitestresult',
            name='raw_status',
            field=models.CharField(blank=True, db_index=True, default='', max_length=32, verbose_name='原始状态'),
        ),
        migrations.AddField(
            model_name='apitestresult',
            name='request_snapshot',
            field=models.JSONField(blank=True, default=dict, verbose_name='请求快照'),
        ),
        migrations.AddField(
            model_name='apitestresult',
            name='response_snapshot',
            field=models.JSONField(blank=True, default=dict, verbose_name='响应快照'),
        ),
        migrations.AddField(
            model_name='apitestresult',
            name='result_metadata',
            field=models.JSONField(blank=True, default=dict, verbose_name='结果元数据'),
        ),
        migrations.AddField(
            model_name='apitestresult',
            name='trace_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='链路追踪ID'),
        ),
        migrations.AddField(
            model_name='testruncaseresult',
            name='error_code',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='testruncaseresult',
            name='extracted_variables_preview',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='testruncaseresult',
            name='raw_status',
            field=models.CharField(blank=True, db_index=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='testruncaseresult',
            name='response_snapshot',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='testruncaseresult',
            name='result_metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='testruncaseresult',
            name='trace_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
    ]
