"""Carries the registered task ids of a job across the side table migration.

Migration ``0029`` moved the ``celery_task_ids`` of a harvesting job from the
array column of its row into one row per id (#892) and, as merged, declared
only the schema operations (#971): a harvest which was running while a
deployment upgraded lost the ids it had registered, and the recovery on the
first worker restart after it answered the now empty shadow with a
re-publication of the whole remaining backlog (#891). The live model carries no
array to seed anymore, so this test travels the real ``MigrationExecutor`` back
to 0028, writes the arrays there the way the old code wrote them and migrates
to 0029 again - which is the upgrade itself, schema operations and the copy
between them.
"""
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CarryTaskIdsAcrossSideTableTest(TransactionTestCase):
    """What the copy of 0029 carries into the side table and what its
    reverse puts back into the array"""

    migrate_from = [
        ('registry', '0028_a_keyword_is_as_long_as_its_catalogue_says')]
    migrate_to = [
        ('registry', '0029_harvestingjob_celery_task_ids_side_table')]

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_schema)

    def old_shape(self):
        """Jobs with the id array of the revision before the side table

        The first entry of an array is the id of the delivery which created
        the job, the rest are the ids of its work. One job registered nothing,
        one registered its creation id alone, and one names a work id which
        another job registered first - a copy which insisted on the unique key
        of the rows would break the upgrade of that pair.

        Returns:
            dict: the primary key of every seeded job and, beside it, the
                task ids which its array named
        """
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        HarvestingJob = apps.get_model('registry', 'HarvestingJob')

        creation, work, shared = uuid4(), uuid4(), uuid4()
        alone, other_creation = uuid4(), uuid4()
        running = HarvestingJob.objects.create(
            celery_task_ids=[creation, work, shared])
        creation_only = HarvestingJob.objects.create(
            celery_task_ids=[alone])
        empty = HarvestingJob.objects.create(celery_task_ids=[])
        borrower = HarvestingJob.objects.create(
            celery_task_ids=[other_creation, shared])
        return {
            'running': (running.pk, creation, work, shared),
            'creation_only': (creation_only.pk, alone),
            'empty': empty.pk,
            'borrower': (borrower.pk, other_creation),
        }

    def task_id_rows(self):
        """The rows of the side table, of the schema under test, by job

        Returns:
            dict: per job id the set of (task id text, creation flag) of
                its rows
        """
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(self.migrate_to).apps
        TaskId = apps.get_model('registry', 'HarvestingJobTaskId')
        rows = {}
        for job_id, task_id, creation in TaskId.objects.values_list(
                'job_id', 'task_id', 'creation'):
            rows.setdefault(job_id, set()).add((str(task_id), bool(creation)))
        return rows

    def test_forwards_splits_the_array_into_rows(self):
        """Every id of a job's array answers from the new table afterwards,
        the first entry of the array as the creation id and the rest as work
        (#971: without these rows the restart after the upgrade re-publishes
        the backlog the messages of which are still queued)"""
        seeded = self.old_shape()
        running_pk, creation, work, shared = seeded['running']
        creation_only_pk, alone = seeded['creation_only']
        empty_pk = seeded['empty']
        borrower_pk, other_creation = seeded['borrower']

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)

        rows = self.task_id_rows()
        self.assertEqual(
            rows.get(running_pk, set()),
            {(str(creation), True), (str(work), False), (str(shared), False)},
            "the ids a running harvest had registered did not cross the "
            "migration, or the creation id was not recognised as such")
        self.assertEqual(rows.get(creation_only_pk, set()), {(str(alone), True)})
        self.assertNotIn(
            empty_pk, rows,
            "a job which registered nothing answers a row it never had")
        self.assertEqual(
            rows.get(borrower_pk, set()), {(str(other_creation), True)},
            "the id one job registered first lost its row to the job which "
            "only names it - the copy must not break the upgrade on it")
        self.assertEqual(
            sum(len(entries) for entries in rows.values()), 5,
            "the side table holds a row the migration did not write")

    def test_backwards_puts_the_rows_back_into_the_array(self):
        """The reverse hands the old code its own shape back: the creation id
        in front, the work of the run behind it, and nothing for a job which
        registered nothing"""
        seeded = self.old_shape()
        running_pk, creation, work, shared = seeded['running']
        creation_only_pk, alone = seeded['creation_only']
        empty_pk = seeded['empty']
        borrower_pk, other_creation = seeded['borrower']

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        HarvestingJob = apps.get_model('registry', 'HarvestingJob')

        self.assertEqual(
            [str(_id) for _id in
             HarvestingJob.objects.get(pk=running_pk).celery_task_ids],
            [str(creation), str(work), str(shared)])
        self.assertEqual(
            [str(_id) for _id in
             HarvestingJob.objects.get(pk=creation_only_pk).celery_task_ids],
            [str(alone)])
        self.assertEqual(
            list(HarvestingJob.objects.get(pk=empty_pk).celery_task_ids), [])
        # the id which two jobs named comes back to the one whose row owned
        # it - the array of the other loses what the forward copy had dropped
        self.assertEqual(
            [str(_id) for _id in
             HarvestingJob.objects.get(pk=borrower_pk).celery_task_ids],
            [str(other_creation)])

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
