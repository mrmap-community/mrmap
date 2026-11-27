"""Carries the registered task ids of a job across the side table migration.

The ``celery_task_ids`` of a harvesting job used to be an array column of its
row; the side table of #892 moved them into one row per id and, since #971,
the move carried the data itself: a harvest which was running while a
deployment upgraded lost the ids it had registered, and the recovery on the
first worker restart after it answered the now empty shadow with a
re-publication of the whole remaining backlog (#891). The rebuilt chain of
#1850 creates the side table from the models and no array at all -- it has no
node at which the array stood and no name of one left to travel to. What this
class proves has survived that: it builds the shape of the deployment which
had the array -- the column added back as the old chain created it, jobs whose
array names its ids -- and runs the two statements the carry carried over
them: the split of the array into rows of the table the rebuilt chain
created, and the way back which puts the rows into the array again.
"""
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase

from registry.models.harvest import HarvestingJob, HarvestingJobTaskId

#: the migration of the rebuilt chain which creates the schema the carry runs
#: on; the plan around it is what the tests run on
INITIAL = ('registry', '0001_initial')

#: splits every job's array into one row per id, the first entry as the
#: creation id; a null or empty array answers no row, and an id which is
#: registered for another job first is dropped rather than breaking the
#: upgrade -- the statement of the carry forward, carried here verbatim from
#: the node of the old chain which ran it
CARRY_FORWARD = """
    INSERT INTO registry_harvestingjobtaskid (job_id, task_id, creation)
    SELECT job.id, registered.task_id, registered.ordinality = 1
      FROM registry_harvestingjob job
 CROSS JOIN LATERAL unnest(job.celery_task_ids)
            WITH ORDINALITY AS registered(task_id, ordinality)
    ON CONFLICT (task_id) DO NOTHING
"""

#: puts the rows of every job back into its array, the creation id in front as
#: the copy read it and the work of a run behind it in the order it was
#: written -- the statement of the carry back, carried here verbatim from the
#: node of the old chain which ran it
CARRY_BACK = """
    UPDATE registry_harvestingjob job
       SET celery_task_ids = carried.ids
      FROM (SELECT job_id,
                   array_agg(task_id ORDER BY creation DESC, id) AS ids
              FROM registry_harvestingjobtaskid
             GROUP BY job_id) carried
     WHERE job.id = carried.job_id
"""


class CarryTaskIdsAcrossSideTableTest(TestCase):
    """What the copy carries into the side table and what its reverse puts
    back into the array.

    ``TransactionTestCase`` was needed while this class rolled the migration
    executor back over the carry node of the old chain; nothing migrates any
    more -- the shape with the array is plain sql inside the transaction of
    the test, which postgres rolls back with it.
    """

    def rebuilt_chain(self):
        """The plan of the rebuilt chain, which the carry runs on."""
        plan = MigrationExecutor(connection).loader.graph.forwards_plan(
            INITIAL)
        self.assertIn(INITIAL, plan)
        return plan

    def chain_side_table(self):
        """The side table of the rebuilt chain, which the carry writes into.

        Read off the migrated test database: the table of #892 stands beside
        the job with its unique key of the task id -- the key the ``ON
        CONFLICT`` of the copy needs to drop the id which another job
        registered first instead of breaking the upgrade on it -- and neither
        the job nor its audit relation answers an array column anymore. The
        copy writes into this table and not into one it made for itself.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT con.conname, array_agg(att.attname ORDER BY 1)"
                " FROM pg_constraint con"
                " JOIN pg_class rel ON rel.oid = con.conrelid"
                " JOIN pg_attribute att"
                "   ON att.attrelid = rel.oid AND att.attnum = ANY (con.conkey)"
                " WHERE rel.relname = %s"
                "   AND rel.relnamespace = 'public'::regnamespace"
                "   AND con.contype = 'u'"
                " GROUP BY con.conname",
                [HarvestingJobTaskId._meta.db_table])
            keys = {frozenset(columns) for _, columns in cursor.fetchall()}
        self.assertIn(
            frozenset({'task_id'}), keys,
            'the rebuilt chain did not create the side table of #892 with '
            'its unique key of the task id')
        with connection.cursor() as cursor:
            for table in (HarvestingJob._meta.db_table,
                          HarvestingJob.change_log.model._meta.db_table):
                cursor.execute(
                    'SELECT 1 FROM information_schema.columns'
                    ' WHERE table_name = %s AND column_name = %s',
                    [table, 'celery_task_ids'])
                self.assertIsNone(
                    cursor.fetchone(),
                    'the rebuilt chain still answers the array column of '
                    '%s, which the side table replaced' % table)

    def old_shape(self):
        """Jobs with the id array of the revision before the side table

        The first entry of an array is the id of the delivery which created
        the job, the rest are the ids of its work. One job registered nothing,
        one registered its creation id alone, and one names a work id which
        another job registered first - a copy which insisted on the unique key
        of the rows would break the upgrade of that pair.

        The array column is added back over the final schema of the rebuilt
        chain exactly as the old chain created it - an array of uuids, one per
        registered id - and the arrays are written by plain sql, because the
        live model carries no array to hand them in.

        Returns:
            dict: the primary key of every seeded job and, beside it, the
                task ids which its array named
        """
        self.rebuilt_chain()
        self.chain_side_table()

        creation, work, shared = uuid4(), uuid4(), uuid4()
        alone, other_creation = uuid4(), uuid4()
        running = HarvestingJob.objects.create()
        creation_only = HarvestingJob.objects.create()
        empty = HarvestingJob.objects.create()
        borrower = HarvestingJob.objects.create()

        with connection.cursor() as cursor:
            # the foreign keys of the chain come up DEFERRABLE INITIALLY
            # DEFERRED and the seeded jobs queued their checks; the old node
            # added its column inside a migration transaction over rows which
            # were committed already, and forcing the pending checks - all of
            # which reference rows which are there - answers that boundary
            # here
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            for table in (HarvestingJob._meta.db_table,
                          HarvestingJob.change_log.model._meta.db_table):
                cursor.execute(
                    'ALTER TABLE "%s" ADD COLUMN "celery_task_ids" uuid[]'
                    % table)
            for pk, ids in ((running.pk, [creation, work, shared]),
                            (creation_only.pk, [alone]),
                            (empty.pk, []),
                            (borrower.pk, [other_creation, shared])):
                cursor.execute(
                    'UPDATE "%s" SET "celery_task_ids" = %%s WHERE "id" = %%s'
                    % HarvestingJob._meta.db_table,
                    [[str(_id) for _id in ids], pk])
        return {
            'running': (running.pk, creation, work, shared),
            'creation_only': (creation_only.pk, alone),
            'empty': empty.pk,
            'borrower': (borrower.pk, other_creation),
        }

    def carry_forward(self):
        """The upgrade itself: the statement which splits the arrays into rows"""
        with connection.cursor() as cursor:
            cursor.execute(CARRY_FORWARD)

    def carry_back(self):
        """The way back: the statement which puts the rows into the arrays"""
        with connection.cursor() as cursor:
            cursor.execute(CARRY_BACK)

    def task_id_rows(self):
        """The rows of the side table, of the schema under test, by job

        Read through the model of the rebuilt chain, so that the copy answers
        through the very table the chain created.

        Returns:
            dict: per job id the set of (task id text, creation flag) of
                its rows
        """
        rows = {}
        for job_id, task_id, creation in HarvestingJobTaskId.objects.values_list(
                'job_id', 'task_id', 'creation'):
            rows.setdefault(job_id, set()).add((str(task_id), bool(creation)))
        return rows

    def array_of(self, pk):
        """The id array a job answers, read by plain sql

        The live model carries no array to hand it in anymore, which is what
        the carry back answers below on its own.

        Returns:
            list: the task ids of the job's array, as text
        """
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT "celery_task_ids" FROM "%s" WHERE "id" = %%s'
                % HarvestingJob._meta.db_table, [pk])
            array = cursor.fetchone()[0]
        return [str(_id) for _id in array] if array else []

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

        self.carry_forward()

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

        self.carry_forward()
        self.carry_back()

        self.assertEqual(
            self.array_of(running_pk),
            [str(creation), str(work), str(shared)])
        self.assertEqual(
            self.array_of(creation_only_pk), [str(alone)])
        self.assertEqual(self.array_of(empty_pk), [])
        # the id which two jobs named comes back to the one whose row owned
        # it - the array of the other loses what the forward copy had dropped
        self.assertEqual(
            self.array_of(borrower_pk), [str(other_creation)])
