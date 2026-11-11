"""Take the stored records of harvests which ended back (#1237).

Every run stores the records it downloaded as rows and files below
``MEDIA_ROOT/temporary_md_metadata_file/``; a run in a terminal phase is done
consuming them, and since #1237 its completion or abort schedules the cleanup
of its own backlog. This command is the operator path over the same cleanup:
for the historical backlog of a deployment which ran before the fix (the demo
rig of the issue: 187,789 rows and some 6.7 GB of ended jobs), and for a job
whose automatic cleanup could not finish. It deletes through the same
bounded, idempotent function the tasks run, so it may meet a running cleanup
or a re-run of itself without either doing damage.

Only jobs in a terminal phase are ever named: a job which is not COMPLETED or
ABORTED keeps every row and file, and a scan without ``--job-id`` additionally
waits out the retention window so a run which ended moments ago is not read
while its own scheduled cleanup is still taking it. Nothing here leaves the
temporary storage location, and nothing here deletes a permanent record.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from registry.enums.harvesting import HarvestingPhaseEnum


class Command(BaseCommand):
    help = ("Delete the stored metadata records (rows and files) which "
            "harvesting jobs in a terminal phase (completed, aborted) still "
            "hold (#1237). Reports with --dry-run; needs --confirm to "
            "delete. Never touches the backlog of a running job.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--job-id", type=int, action="append", dest="job_ids",
            metavar="ID", help="only this job (repeatable); named jobs are "
            "cleaned without waiting out the retention")
        parser.add_argument(
            "--dry-run", action="store_true", help="report what would go, "
            "delete nothing")
        parser.add_argument(
            "--confirm", action="store_true", help="actually delete; without "
            "it and without --dry-run the command refuses")
        parser.add_argument(
            "--older-than", type=int, metavar="DAYS", default=None,
            help="jobs must have ended this many days ago (default: "
            "HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS); ignored for "
            "--job-id")
        parser.add_argument(
            "--batch-size", type=int, default=None, help="rows per database "
            "batch (default: HARVEST_TEMP_FILE_CLEANUP_BATCH_SIZE)")
        parser.add_argument(
            "--limit", type=int, default=None, metavar="ROWS",
            help="delete at most this many rows per job in this run "
            "(default: HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN); the "
            "command can be interrupted and re-run whenever")

    def handle(self, *args, **options):
        # the tasks module carries the cleanup; importing models at module
        # level is what its import cycle punishes, so this speaks on their
        # behalf like resume_harvesting_job does
        from registry.models.harvest import (HarvestingJob,
                                             TemporaryMdMetadataFile)
        from registry.tasks.harvest import cleanup_harvesting_job_temp_files

        if not options["dry_run"] and not options["confirm"]:
            self.stderr.write(self.style.ERROR(
                "this deletes rows and the media files they reference. Run "
                "with --dry-run to see the scope, or with --confirm to "
                "delete"))
            raise SystemExit(1)

        jobs = HarvestingJob.objects.filter(
            phase__in=[HarvestingPhaseEnum.COMPLETED.value,
                       HarvestingPhaseEnum.ABORTED.value])
        if options["job_ids"]:
            jobs = jobs.filter(pk__in=options["job_ids"])
            missing = set(options["job_ids"]) - set(
                jobs.values_list("pk", flat=True))
            for pk in sorted(missing):
                self.stderr.write(self.style.WARNING(
                    f"harvesting job {pk} is not a terminal job to clean "
                    "(it may run, may not exist, or is already cleaned up "
                    "to zero rows and an empty directory)"))
        else:
            from django.conf import settings
            days = (options["older_than"] if options["older_than"] is not None
                    else getattr(settings,
                                 "HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS", 1))
            cutoff = timezone.now() - timedelta(days=max(0, days))
            jobs = jobs.filter(done_at__lt=cutoff)

        jobs = jobs.order_by("pk")

        if options["dry_run"]:
            total_rows = 0
            for job in jobs:
                rows = TemporaryMdMetadataFile.objects.filter(
                    job_id=job.pk).count()
                if not rows:
                    continue
                total_rows += rows
                self.stdout.write(
                    f"job {job.pk} ({HarvestingPhaseEnum(job.phase).label}): "
                    f"{rows} stored records would be deleted")
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"{jobs.count()} terminal jobs are in scope, "
                f"{total_rows} stored records would be deleted "
                "(nothing was)"))
            return

        for job in jobs.iterator():
            if not TemporaryMdMetadataFile.objects.filter(
                    job_id=job.pk).exists():
                continue
            summary = cleanup_harvesting_job_temp_files(
                job.pk, batch_size=options["batch_size"],
                max_rows=options["limit"])
            self.stdout.write(
                f"job {job.pk}: {summary['rows']} rows and {summary['files']} "
                f"files deleted, {summary['missing']} already gone, "
                f"{summary['failed']} + {summary['swept_failed']} file "
                f"failures, {summary['rejected']} names refused, "
                f"{summary['swept_files']} swept, "
                f"rows left: {summary['remaining_rows']} "
                f"({summary['seconds']} s)")
            if summary["remaining_rows"] or summary["failed"] or \
                    summary["rejected"] or summary["swept_failed"] or \
                    summary["sweep_remaining"]:
                self.stdout.write(self.style.WARNING(
                    f"job {job.pk} is not clean yet - run the command again, "
                    "the cleanup continues where it stopped"))
