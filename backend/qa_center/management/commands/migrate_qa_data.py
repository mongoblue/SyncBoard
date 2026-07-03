"""One-shot data migration for QA Center production upgrade (Task 13).

Run with:
    python manage.py migrate_qa_data [--dry-run]

Operations:
1. _migrate_pipeline_status: backfill is_mock flag on PipelineRun records
2. _mark_mock_data: mark PipelineRun records without external_run_id as mock
"""

import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Migrate QA Center data for production upgrade (Task 13)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing to database",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write("=" * 60)
        self.stdout.write("QA Center Data Migration (Task 13)")
        self.stdout.write("=" * 60)

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY-RUN] No changes will be written."))

        self._migrate_pipeline_status(dry_run)
        self._mark_mock_data(dry_run)

        self.stdout.write(self.style.SUCCESS("Migration complete."))

    # ------------------------------------------------------------------
    # Pipeline status migration
    # ------------------------------------------------------------------

    def _migrate_pipeline_status(self, dry_run: bool):
        """Backfill is_mock flag on PipelineRun records.

        - Records with external_run_id set: is_mock = False
        - Records without external_run_id: is_mock = True (handled by _mark_mock_data)
        """
        from qa_center.models import PipelineRun

        total = PipelineRun.objects.count()
        if total == 0:
            self.stdout.write("  No PipelineRun records found. Skipping.")
            return

        self.stdout.write(f"\n[1/2] Pipeline status migration ({total} records)")

        # Count current state
        with_ext = PipelineRun.objects.exclude(external_run_id="").count()
        without_ext = total - with_ext

        self.stdout.write(f"  With external_run_id:    {with_ext}")
        self.stdout.write(f"  Without external_run_id: {without_ext}")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"  [DRY-RUN] Would set is_mock=False on {with_ext} records"
            ))
            return

        # Set is_mock=False for records that have external_run_id
        updated = PipelineRun.objects.exclude(external_run_id="").update(is_mock=False)
        self.stdout.write(self.style.SUCCESS(f"  Updated {updated} records (is_mock=False)"))

    # ------------------------------------------------------------------
    # Mark mock data
    # ------------------------------------------------------------------

    def _mark_mock_data(self, dry_run: bool):
        """Mark PipelineRun records without external_run_id as mock data.

        These are records created before the real CI integration (Task 8)
        and represent simulated pipeline runs.
        """
        from qa_center.models import PipelineRun

        total = PipelineRun.objects.filter(external_run_id="").count()
        if total == 0:
            self.stdout.write("\n[2/2] No mock PipelineRun records. Skipping.")
            return

        self.stdout.write(f"\n[2/2] Mark mock PipelineRun records ({total} records)")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"  [DRY-RUN] Would set is_mock=True on {total} records"
            ))
            return

        updated = PipelineRun.objects.filter(external_run_id="").update(is_mock=True)
        self.stdout.write(self.style.SUCCESS(f"  Marked {updated} records as mock"))
