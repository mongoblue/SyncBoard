"""0023 修复 ApiAutoTestCase/ApiAutoTestResult.project_id 列类型。

0022 迁移手写 raw SQL 时把 project_id 当成 bigint 加，但 room_project.id 是
char(32)（UUID）。本迁移把列类型改成 char(32) 并重建 FK。
"""
from django.db import migrations


def _fix_table(cur, table, fk_name):
    # 1. drop 所有 project_id 上的 FK（清理 0022 遗留的孤儿 FK + 正确 FK）
    cur.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME='project_id' "
        "AND REFERENCED_TABLE_NAME IS NOT NULL",
        [table],
    )
    for r in cur.fetchall():
        try:
            cur.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{r[0]}`")
        except Exception:
            pass
    # 2. drop 列上的索引（用 SHOW INDEX 拿真实存在的）
    cur.execute(f"SHOW INDEX FROM `{table}`")
    indexes = set()
    for r in cur.fetchall():
        if r[4] == 'project_id':
            indexes.add(r[2])
    for idx in indexes:
        try:
            cur.execute(f"ALTER TABLE `{table}` DROP INDEX `{idx}`")
        except Exception:
            pass
    # 3. 改列类型为 char(32)
    cur.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `project_id` CHAR(32) NULL")
    # 4. 重建索引 + FK
    cur.execute(
        f"ALTER TABLE `{table}` ADD INDEX `{table}_project_id_idx` (`project_id`)"
    )
    cur.execute(
        f"ALTER TABLE `{table}` ADD CONSTRAINT `{fk_name}` "
        f"FOREIGN KEY (`project_id`) REFERENCES `project`(`id`)"
    )


def fix_project_fk(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        _fix_table(cur, 'qa_api_auto_cases', 'qa_api_auto_cases_project_id_fk')
        _fix_table(cur, 'qa_api_auto_results', 'qa_api_auto_results_project_id_fk')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ('qa_center', '0022_merge_api_case_models'),
    ]
    operations = [
        migrations.RunPython(fix_project_fk, noop),
    ]
