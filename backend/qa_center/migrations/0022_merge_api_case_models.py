"""合并 API 测试用例模型：删除 legacy ApiTestCase/ApiTestResult，扩展 ApiAutoTestCase。

破坏式迁移：开发环境丢弃老数据。
- Drop: qa_api_test_cases, qa_api_test_results
- Remove: TestResult.api_test_case FK
- Replace: TestRunCaseResult.api_test_case -> api_auto_case (指向新模型)
- Add: ApiAutoTestCase.project, ApiAutoTestCase.environment
- Alter: ApiAutoTestCase.suite nullable, ApiAutoTestResult.suite nullable + project FK
- Add: ApiAutoTestCaseResult.failure_type

可重入：前次失败的迁移可能已经部分应用，所有 DB 操作都先 introspect 再执行。
"""
from django.db import migrations, models


def _column_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return cur.fetchone() is not None


def _index_exists(cur, table, index_name):
    cur.execute(
        "SELECT 1 FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s "
        "LIMIT 1",
        [table, index_name],
    )
    return cur.fetchone() is not None


def _fk_names(cur, table, column):
    cur.execute(
        "SELECT constraint_name FROM information_schema.key_column_usage "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s "
        "AND referenced_table_name IS NOT NULL",
        [table, column],
    )
    return [row[0] for row in cur.fetchall()]


def _drop_column_if_exists(schema_editor, table, column):
    cur = schema_editor.connection.cursor()
    if _column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")


def _drop_fks_if_exist(schema_editor, table, column):
    cur = schema_editor.connection.cursor()
    for name in _fk_names(cur, table, column):
        cur.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`")


def _drop_index_if_exists(schema_editor, table, index_name):
    cur = schema_editor.connection.cursor()
    if _index_exists(cur, table, index_name):
        cur.execute(f"DROP INDEX `{index_name}` ON `{table}`")


def _add_column_if_missing(schema_editor, table, column, ddl):
    cur = schema_editor.connection.cursor()
    if not _column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE `{table}` ADD COLUMN {ddl}")


def _add_index_if_missing(schema_editor, table, index_name, ddl):
    cur = schema_editor.connection.cursor()
    if not _index_exists(cur, table, index_name):
        cur.execute(f"CREATE INDEX `{index_name}` ON `{table}` {ddl}")


def _drop_testresult_api_test_case_fk(apps, schema_editor):
    _drop_fks_if_exist(schema_editor, 'qa_test_results', 'api_test_case_id')
    _drop_column_if_exists(schema_editor, 'qa_test_results', 'api_test_case_id')


def _drop_testruncaseresult_api_test_case_index(apps, schema_editor):
    _drop_index_if_exists(schema_editor, 'qa_test_run_case_results', 'qa_test_run_api_tes_6621dc_idx')


def _drop_testruncaseresult_api_test_case_fk(apps, schema_editor):
    _drop_fks_if_exist(schema_editor, 'qa_test_run_case_results', 'api_test_case_id')
    _drop_column_if_exists(schema_editor, 'qa_test_run_case_results', 'api_test_case_id')


def _add_testruncaseresult_api_auto_case(apps, schema_editor):
    _add_column_if_missing(
        schema_editor, 'qa_test_run_case_results', 'api_auto_case_id',
        '`api_auto_case_id` bigint NULL',
    )


def _add_testruncaseresult_api_auto_case_fk(apps, schema_editor):
    cur = schema_editor.connection.cursor()
    if not _fk_names(cur, 'qa_test_run_case_results', 'api_auto_case_id'):
        cur.execute(
            "ALTER TABLE `qa_test_run_case_results` "
            "ADD CONSTRAINT `qa_test_run_caseres_api_auto_case_id_fk` "
            "FOREIGN KEY (`api_auto_case_id`) REFERENCES `qa_api_auto_cases`(`id`)"
        )


def _add_testruncaseresult_api_auto_case_index(apps, schema_editor):
    _add_index_if_missing(
        schema_editor, 'qa_test_run_case_results', 'qa_test_run_api_aut_a207a7_idx',
        '(`api_auto_case_id`, `completed_at` DESC)',
    )


def _add_apiautotestcase_project(apps, schema_editor):
    _add_column_if_missing(
        schema_editor, 'qa_api_auto_cases', 'project_id',
        '`project_id` bigint NULL',
    )
    cur = schema_editor.connection.cursor()
    if not _fk_names(cur, 'qa_api_auto_cases', 'project_id'):
        cur.execute(
            "ALTER TABLE `qa_api_auto_cases` "
            "ADD CONSTRAINT `qa_api_auto_cases_project_id_fk` "
            "FOREIGN KEY (`project_id`) REFERENCES `room_project`(`id`)"
        )


def _add_apiautotestcase_environment(apps, schema_editor):
    _add_column_if_missing(
        schema_editor, 'qa_api_auto_cases', 'environment_id',
        '`environment_id` bigint NULL',
    )
    cur = schema_editor.connection.cursor()
    if not _fk_names(cur, 'qa_api_auto_cases', 'environment_id'):
        cur.execute(
            "ALTER TABLE `qa_api_auto_cases` "
            "ADD CONSTRAINT `qa_api_auto_cases_environment_id_fk` "
            "FOREIGN KEY (`environment_id`) REFERENCES `qa_test_environments`(`id`)"
        )


def _alter_apiautotestcase_suite_nullable(apps, schema_editor):
    cur = schema_editor.connection.cursor()
    cur.execute("ALTER TABLE `qa_api_auto_cases` MODIFY COLUMN `suite_id` bigint NULL")


def _add_apiautotestcaseresult_failure_type(apps, schema_editor):
    _add_column_if_missing(
        schema_editor, 'qa_api_auto_case_results', 'failure_type',
        "`failure_type` varchar(32) NOT NULL DEFAULT ''",
    )
    cur = schema_editor.connection.cursor()
    if not _index_exists(cur, 'qa_api_auto_case_results', 'qa_api_auto_case_r_failure_t_idx'):
        cur.execute(
            "CREATE INDEX `qa_api_auto_case_r_failure_t_idx` "
            "ON `qa_api_auto_case_results` (`failure_type`)"
        )


def _alter_apiautotestresult_suite_nullable(apps, schema_editor):
    cur = schema_editor.connection.cursor()
    cur.execute("ALTER TABLE `qa_api_auto_results` MODIFY COLUMN `suite_id` bigint NULL")


def _add_apiautotestresult_project(apps, schema_editor):
    _add_column_if_missing(
        schema_editor, 'qa_api_auto_results', 'project_id',
        '`project_id` bigint NULL',
    )
    cur = schema_editor.connection.cursor()
    if not _fk_names(cur, 'qa_api_auto_results', 'project_id'):
        cur.execute(
            "ALTER TABLE `qa_api_auto_results` "
            "ADD CONSTRAINT `qa_api_auto_results_project_id_fk` "
            "FOREIGN KEY (`project_id`) REFERENCES `room_project`(`id`)"
        )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('qa_center', '0021_legacy_result_unified_fields'),
        ('room', '0001_initial'),
    ]

    operations = [
        # 0. MySQL 在 DROP TABLE 时会因 FK 引用拒绝，先关闭 FK 检查
        migrations.RunSQL("SET FOREIGN_KEY_CHECKS = 0;"),

        # 1. 先移除所有指向 ApiTestCase 的 FK 和 index（必须在 DeleteModel 之前）
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='testresult', name='api_test_case'),
            ],
            database_operations=[
                migrations.RunPython(_drop_testresult_api_test_case_fk, migrations.RunPython.noop),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name='testruncaseresult',
                    name='qa_test_run_api_tes_6621dc_idx',
                ),
            ],
            database_operations=[
                migrations.RunPython(_drop_testruncaseresult_api_test_case_index, migrations.RunPython.noop),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='testruncaseresult', name='api_test_case'),
            ],
            database_operations=[
                migrations.RunPython(_drop_testruncaseresult_api_test_case_fk, migrations.RunPython.noop),
            ],
        ),

        # 2. 删除 legacy 模型对应的表
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='ApiTestResult'),
                migrations.DeleteModel(name='ApiTestCase'),
            ],
            database_operations=[
                migrations.RunSQL("DROP TABLE IF EXISTS qa_api_test_results;", migrations.RunSQL.noop),
                migrations.RunSQL("DROP TABLE IF EXISTS qa_api_test_cases;", migrations.RunSQL.noop),
            ],
        ),

        # 3. TestRunCaseResult: 新增 api_auto_case FK + index
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='testruncaseresult',
                    name='api_auto_case',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.SET_NULL,
                        related_name='run_case_results',
                        to='qa_center.apiautotestcase',
                        verbose_name='关联API用例',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_testruncaseresult_api_auto_case, migrations.RunPython.noop),
                migrations.RunPython(_add_testruncaseresult_api_auto_case_fk, migrations.RunPython.noop),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name='testruncaseresult',
                    index=models.Index(
                        fields=['api_auto_case', '-completed_at'],
                        name='qa_test_run_api_aut_a207a7_idx',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_testruncaseresult_api_auto_case_index, migrations.RunPython.noop),
            ],
        ),

        # 4. ApiAutoTestCase: suite nullable + project/environment
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='apiautotestcase',
                    name='suite',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.CASCADE,
                        related_name='test_cases',
                        to='qa_center.apiautotestsuite',
                        verbose_name='所属套件',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_alter_apiautotestcase_suite_nullable, migrations.RunPython.noop),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='apiautotestcase',
                    name='project',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.CASCADE,
                        related_name='api_auto_cases',
                        to='room.project',
                        verbose_name='所属项目',
                        help_text='独立用例直接绑定项目；为空时回退到 suite.project',
                    ),
                    preserve_default=False,
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_apiautotestcase_project, migrations.RunPython.noop),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='apiautotestcase',
                    name='environment',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.SET_NULL,
                        related_name='api_auto_cases',
                        to='qa_center.testenvironment',
                        verbose_name='绑定环境',
                        help_text='用例级环境覆盖；为空时回退到项目默认环境',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_apiautotestcase_environment, migrations.RunPython.noop),
            ],
        ),

        # 5. ApiAutoTestCaseResult: 加 failure_type
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='apiautotestcaseresult',
                    name='failure_type',
                    field=models.CharField(
                        blank=True, db_index=True, default='',
                        help_text='passed/assertion_failed/http_error/network_error/timeout/ssl_error/auth_error/server_error/framework_error/config_error/script_error/schema_failed/unknown_error',
                        max_length=32,
                        verbose_name='失败类型',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_apiautotestcaseresult_failure_type, migrations.RunPython.noop),
            ],
        ),

        # 6. ApiAutoTestResult: suite nullable + project FK
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='apiautotestresult',
                    name='suite',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.CASCADE,
                        related_name='test_results',
                        to='qa_center.apiautotestsuite',
                        verbose_name='测试套件',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_alter_apiautotestresult_suite_nullable, migrations.RunPython.noop),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='apiautotestresult',
                    name='project',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.CASCADE,
                        related_name='api_auto_test_results',
                        to='room.project',
                        verbose_name='所属项目',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_apiautotestresult_project, migrations.RunPython.noop),
            ],
        ),

        # 7. 恢复 FK 检查
        migrations.RunSQL("SET FOREIGN_KEY_CHECKS = 1;"),
    ]
