"""The operator command over the cleanup of #1237.

The command deletes through ``cleanup_harvesting_job_temp_files`` like the
tasks do; these tests answer the operator-facing questions: it refuses before
it was told, reports without deleting, only names terminal jobs, waits out the
retention when it scans, and bounds a run when it is told to.
"""

from io import StringIO
from tempfile import TemporaryDirectory
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile


class CleanupTemporaryHarvestFilesCommandTest(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media = override_settings(MEDIA_ROOT=self.media.name)
        media.enable()
        self.addCleanup(media.disable)
        self.out = StringIO()
        self.err = StringIO()

    def job(self, phase=Phase.COMPLETED, ended_days_ago=3):
        job = HarvestingJob(
            total_records=0, phase=phase,
            done_at=timezone.now() - timedelta(days=ended_days_ago))
        HarvestingJob.objects.bulk_create([job])
        return job

    def stored(self, job, name):
        record = TemporaryMdMetadataFile(job=job)
        record.md_metadata_file.save(name, ContentFile(b'<record/>'),
                                     save=False)
        TemporaryMdMetadataFile.objects.bulk_create([record])
        return record

    def storage(self):
        return TemporaryMdMetadataFile._meta.get_field(
            'md_metadata_file').storage

    def run_command(self, *args):
        call_command('cleanup_temporary_harvest_files', *args,
                     stdout=self.out, stderr=self.err)
        return self.out.getvalue()

    def test_it_refuses_before_it_was_told(self):
        with self.assertRaises(SystemExit):
            self.run_command()
        self.assertIn('--dry-run', self.err.getvalue())
        self.assertIn('--confirm', self.err.getvalue())

    def test_dry_run_reports_without_deleting_anything(self):
        ended = self.job()
        record = self.stored(ended, 'held.xml')
        self.stored(ended, 'held2.xml')
        running = self.job(phase=Phase.RECORDS_TO_DB)
        self.stored(running, 'in-progress.xml')

        answer = self.run_command('--dry-run')

        self.assertIn(f'job {ended.pk}', answer)
        self.assertIn('2 stored records would be deleted', answer)
        self.assertNotIn(f'job {running.pk} (', answer)
        self.assertIn('nothing was', answer)
        self.assertEqual(TemporaryMdMetadataFile.objects.count(), 3)
        self.assertTrue(self.storage().exists(record.md_metadata_file.name))

    def test_confirm_takes_the_backlog_of_the_ended_jobs_only(self):
        ended = self.job()
        record = self.stored(ended, 'held.xml')
        running = self.job(phase=Phase.RECORDS_TO_DB)
        kept = self.stored(running, 'in-progress.xml')

        answer = self.run_command('--confirm')

        self.assertIn(f'job {ended.pk}', answer)
        self.assertIn('1 rows and 1 files deleted', answer)
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            job_id=ended.pk).exists())
        self.assertFalse(self.storage().exists(record.md_metadata_file.name))
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(
            pk=kept.pk).exists())
        self.assertTrue(self.storage().exists(kept.md_metadata_file.name))

    def test_a_named_job_is_cleaned_without_waiting_out_the_retention(self):
        just_ended = self.job(ended_days_ago=0)
        record = self.stored(just_ended, 'fresh.xml')

        answer = self.run_command('--confirm', '--job-id', str(just_ended.pk))

        self.assertIn(f'job {just_ended.pk}', answer)
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            job_id=just_ended.pk).exists())
        self.assertFalse(self.storage().exists(record.md_metadata_file.name))

    def test_a_named_job_which_is_no_terminal_backlog_is_only_warned_about(
            self):
        running = self.job(phase=Phase.RECORDS_TO_DB)
        self.stored(running, 'in-progress.xml')

        answer = self.run_command('--confirm', '--job-id', str(running.pk),
                          '--job-id', '123456789')

        self.assertIn(str(running.pk), self.err.getvalue())
        self.assertIn('123456789', self.err.getvalue())
        self.assertNotIn(f'job {running.pk}:', answer)
        self.assertEqual(TemporaryMdMetadataFile.objects.count(), 1)

    def test_a_scan_waits_out_the_retention_and_older_than_overrides_it(self):
        young = self.job(ended_days_ago=0)
        self.stored(young, 'young.xml')

        answer = self.run_command('--dry-run')
        self.assertIn('0 stored records would be deleted', answer)

        answer = self.run_command('--dry-run', '--older-than', '0')
        self.assertIn(f'job {young.pk}', answer)

    def test_the_limit_bounds_one_job_and_asks_for_another_run(self):
        ended = self.job()
        first = self.stored(ended, 'a.xml')
        second = self.stored(ended, 'b.xml')

        answer = self.run_command('--confirm', '--limit', '1')

        self.assertIn(f'job {ended.pk}', answer)
        self.assertIn('rows left: True', answer)
        self.assertIn('not clean yet', answer)
        left = TemporaryMdMetadataFile.objects.filter(job_id=ended.pk)
        self.assertEqual(left.count(), 1)
        remaining = left.get().md_metadata_file.name
        self.assertIn(remaining, (first.md_metadata_file.name,
                                  second.md_metadata_file.name))
        gone = (first if remaining == second.md_metadata_file.name else second)
        self.assertFalse(self.storage().exists(gone.md_metadata_file.name))

        # the next run continues where the bounded one stopped
        self.run_command('--confirm')
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            job_id=ended.pk).exists())
        self.assertFalse(self.storage().exists(remaining))
