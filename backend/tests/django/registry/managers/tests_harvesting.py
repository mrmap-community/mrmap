"""The task read plans behind the harvesting aggregate (#1397).

Two promises are tested here. ``TemporaryMdMetadataFile``'s
``for_harvest_import()`` answers one locked row with the chain its import
reads — and stays bounded against the backlog the import drains: the file's
statement costs the same with 0, 1 or 10 further files on the job's backlog,
which is the do-not-prefetch-the-backlog case of the conventions. And the
composition of ``HarvestingJobManager`` (``DefaultHistoryManager`` +
``CTEManager`` returning ``HarvestingJobQuerySet``) stays intact, so later
manager-first migrations of this aggregate (#1392) have a green line to stay
on.
"""
from django.test import TestCase
from django_cte import CTEManager, CTEQuerySet
from extras.managers import DefaultHistoryManager
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.managers.harvesting import (HarvestingJobManager,
                                         TemporaryMdMetadataFileManager,
                                         TemporaryMdMetadataFileQuerySet)
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.querys.harvesting import HarvestingJobQuerySet

from tests.django.utils import QUERY_TABLE_RE, QueryPlanMixin


class ForHarvestImportTest(QueryPlanMixin, TestCase):
    """the plan of ``import_md_metadata_file`` (#1397)"""

    def _stored(self, backlog=0):
        """a harvesting job with one stored file to import and `backlog`
        further files waiting behind it on the backlog"""
        job = HarvestingJob.objects.create(
            total_records=backlog + 1, phase=Phase.RECORDS_TO_DB)
        target = TemporaryMdMetadataFile.objects.bulk_create(
            [TemporaryMdMetadataFile(job=job)])[0]
        if backlog:
            TemporaryMdMetadataFile.objects.bulk_create(
                [TemporaryMdMetadataFile(job=job) for _ in range(backlog)])
        return job, target

    def _locked_fetch(self, pk):
        """the fetch of the import: the plan of the row, while the lock
        stays an explicit call-site operation (rule 3 of #1397)"""
        return (TemporaryMdMetadataFile.objects
                .for_harvest_import()
                .select_for_update(of=("self",))
                .filter(pk=pk).first())

    def test_plan_is_the_inline_plan_of_the_import(self):
        """before/after: the method answers the same SQL the import used to
        write inline — the three joins and nothing else"""
        planned = str(
            TemporaryMdMetadataFile.objects.for_harvest_import().query)
        inline = str(TemporaryMdMetadataFile.objects.select_related(
            'job', 'job__service', 'job__service__auth').query)
        self.assertEqual(planned, inline)

    def test_fetch_stays_bounded_against_the_backlog(self):
        """one locked row costs one statement however full its job's backlog
        is — a plan prefetching the backlog would read it per imported file"""
        for backlog in (0, 1, 10):
            with self.subTest(backlog=backlog):
                job, target = self._stored(backlog)
                fetched, sqls = self.measure(self._locked_fetch, target.pk)

                self.assertEqual(1, len(sqls))
                self.assertEqual(job.pk, fetched.job.pk)
                # the chain of the import is cached off the one statement:
                # job and (absent) service answer no further read
                _, job_reads = self.measure(lambda: fetched.job)
                _, service_reads = self.measure(
                    lambda: fetched.job.service)
                self.assertEqual([], job_reads)
                self.assertEqual([], service_reads)
                self.assertIsNone(fetched.job.service)
                # the backlog was not read: the stored-file table appears
                # exactly once in FROM/JOIN position, no self-join
                file_table = TemporaryMdMetadataFile._meta.db_table
                self.assertEqual(
                    1, QUERY_TABLE_RE.findall(sqls[0]).count(file_table))

    def test_method_is_lazy_and_stays_chainable(self):
        _, target = self._stored()

        def wire():
            # building and extending the plan must not hit the database
            return (TemporaryMdMetadataFile.objects
                    .for_harvest_import().using('default')
                    .filter(pk=target.pk))

        _, wiring_reads = self.measure(wire)
        self.assertEqual([], wiring_reads)

        _, reads = self.measure(
            lambda: TemporaryMdMetadataFile.objects
            .for_harvest_import().get(pk=target.pk))
        self.assertEqual(1, len(reads))
        _, reads = self.measure(
            lambda: list(TemporaryMdMetadataFile.objects
                         .for_harvest_import().iterator()))
        self.assertEqual(1, len(reads))

    def test_manager_composition_is_kept(self):
        """the from_queryset exposure keeps the manager of the model — the
        scheduling of `bulk_create_with_task_scheduling` included"""
        manager = TemporaryMdMetadataFile._default_manager
        self.assertIsInstance(manager, TemporaryMdMetadataFileManager)
        self.assertIsInstance(
            manager.get_queryset(), TemporaryMdMetadataFileQuerySet)
        self.assertTrue(callable(
            getattr(manager, 'bulk_create_with_task_scheduling', None)))


class HarvestingJobManagerCompositionTest(QueryPlanMixin, TestCase):
    """manager-first changes must not break the inherited composition"""

    def test_history_and_cte_composition_is_the_manager_of_the_model(self):
        manager = HarvestingJob._default_manager
        self.assertIsInstance(manager, HarvestingJobManager)
        self.assertIsInstance(manager, CTEManager)
        self.assertIsInstance(manager, DefaultHistoryManager)
        queryset = manager.get_queryset()
        self.assertIsInstance(queryset, HarvestingJobQuerySet)
        self.assertIsInstance(queryset, CTEQuerySet)

    def test_history_manager_answers_through_the_composition(self):
        """the DefaultHistoryManager half of the composition still resolves
        its queries: the first-history queryset of the manager reads the run's
        history model spelled through the ``change_logs`` relation"""
        history_model = HarvestingJob.change_log.model
        queryset, reads = self.measure(
            lambda: HarvestingJob.objects.filter_first_history())
        self.assertEqual(history_model, queryset.model)
        count, reads = self.measure(lambda: queryset.count())
        self.assertEqual(0, count)
        self.assertEqual(1, len(reads))

    def test_run_created_at_fallback_of_the_querysets_count(self):
        """the CTEQuerySet half of the composition still answers: the
        queryset carries the count the view read for it (#885)"""
        HarvestingJob.objects.create(total_records=1, phase=Phase.PENDING)
        counted, reads = self.measure(
            lambda: HarvestingJob.objects
            .get_queryset().with_cached_count(42).count())
        self.assertEqual(42, counted)
        self.assertEqual([], reads)
