"""Fills the moment a run was made for the runs a deployment already has.

Migration ``0035`` gave ``ProcessingData.date_created`` the ``default=now`` its sibling in
``notify/models.py`` already has and, beside the two ``AlterField``, the ``UPDATE`` which fills the
runs a deployment already has from the earliest row of their change log (#1079). The live model
cannot seed the shape that fill is about: it answers a creation for every row it is handed, so the
empty column which has to be filled does not exist anymore. So this test travels the real
``MigrationExecutor`` back to 0034, writes the runs and their change log the way an installation
which harvested for years has them, and migrates to 0035 again - which is the upgrade itself, the
schema of the column and the fill of its values.
"""
from datetime import datetime, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

#: the moments of the seeded change log, in the order of a deployment's own history
CREATED = datetime(2023, 3, 14, 7, 30, 12, 451223, tzinfo=timezone.utc)
PROGRESSED = datetime(2023, 3, 14, 7, 34, 5, 917004, tzinfo=timezone.utc)
OWN_MOMENT = datetime(2024, 11, 2, 16, 45, 0, 128003, tzinfo=timezone.utc)
ALREADY_LOGGED = datetime(2024, 11, 2, 16, 44, 58, 405990, tzinfo=timezone.utc)


class HarvestingRunMomentMigrationTest(TransactionTestCase):
    """What the fill of 0035 writes from the change log and what it leaves alone"""

    migrate_from = [
        ('registry', '0034_remove_harvestedmetadatarelation_dm_record_or_sm_record_and_more')]
    migrate_to = [
        ('registry', '0035_a_harvesting_run_knows_when_it_was_made')]

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_schema)

    def old_shape(self):
        """Runs of a deployment which harvested before this migration existed

        The rows are written under the schema of 0034, where the column answers nothing on its own
        and every value in it was written by hand:

        * a run whose change log names its creation and a later revision - the fill has to pick the
          earliest row and not the newest one of the log;
        * a run whose revisions were written newest first, which pins that "earliest" is read from
          the moment of a row and not from the order the rows went in;
        * a run which already answered a moment of its own while its change log names an earlier
          one - a column which holds a value is not overwritten by a derived guess;
        * a run whose change log is gone (revisions are pruned, and a row can predate the audit
          trail) - it keeps the empty value instead of being given an invented date.

        Returns:
            dict: the primary key of every seeded run beside the moment it has to answer
                afterwards, and the number of change log rows the seed wrote
        """
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        HarvestingJob = apps.get_model('registry', 'HarvestingJob')
        ChangeLog = apps.get_model('registry', 'HistoricalHarvestingJob')

        def revision(job, moment):
            """One row of a change log, as simple_history writes it for a save

            The change log mirrors the id of the run it describes in its own ``id``, so that is
            handed over; ``history_id`` is a uuid and answers its own default.
            """
            return ChangeLog.objects.create(
                id=job.pk, history_relation_id=job.pk,
                history_date=moment, history_type='+')

        filled = HarvestingJob.objects.create()
        revision(filled, CREATED)
        revision(filled, PROGRESSED)

        earliest_last = HarvestingJob.objects.create()
        revision(earliest_last, PROGRESSED)
        revision(earliest_last, CREATED)

        own_moment = HarvestingJob.objects.create(date_created=OWN_MOMENT)
        revision(own_moment, ALREADY_LOGGED)

        without_log = HarvestingJob.objects.create()

        return {
            'filled': (filled.pk, CREATED),
            'earliest_last': (earliest_last.pk, CREATED),
            'own_moment': (own_moment.pk, OWN_MOMENT),
            'without_log': (without_log.pk, None),
            'revisions': ChangeLog.objects.count(),
        }

    def moments(self, state):
        """The moment every run answers, read under the schema of ``state``

        Args:
            state: the project state to read the runs with, so that the same assertion answers
                under the schema before and after the fill

        Returns:
            dict: per run id the moment its column answers
        """
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(state).apps
        HarvestingJob = apps.get_model('registry', 'HarvestingJob')
        return dict(HarvestingJob.objects.values_list('pk', 'date_created'))

    def revision_count(self):
        """The rows of the change log under the schema the migration leaves behind"""
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(self.migrate_to).apps
        ChangeLog = apps.get_model('registry', 'HistoricalHarvestingJob')
        return ChangeLog.objects.count()

    def test_forwards_fills_the_runs_the_change_log_knows(self):
        """Every run whose own change log records its creation answers that moment afterwards, a
        run which already answered a moment keeps it, and a run without a change log stays empty
        (#1079: the list of runs of #1087 orders the old runs below the new ones only once the
        column holds the moment a deployment already has somewhere else)"""
        seeded = self.old_shape()
        filled_pk, expected_creation = seeded['filled']
        earliest_pk, expected_earliest = seeded['earliest_last']
        own_pk, expected_own = seeded['own_moment']
        empty_pk, expected_nothing = seeded['without_log']

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)

        moments = self.moments(self.migrate_to)
        self.assertEqual(moments.get(filled_pk), expected_creation)
        self.assertEqual(moments.get(earliest_pk), expected_earliest)
        self.assertEqual(
            moments.get(own_pk), expected_own,
            "the fill overwrote a moment the column already answered with one it derived")
        self.assertIsNone(
            moments.get(empty_pk),
            "a run whose change log is gone was given a date nobody knows")
        self.assertEqual(
            self.revision_count(), seeded['revisions'],
            "the migration wrote a revision of its own - the moment it fills is read from the "
            "change log, it does not belong in it")

    def test_backwards_keeps_the_recovered_moments(self):
        """The reverse of the fill is nothing on purpose: the moments it wrote came out of the
        change log of the deployment and stay true after a downgrade, so a rollback does not throw
        away what the upgrade recovered. The schema of the column does go back, so an older version
        reads the same runs it wrote before"""
        seeded = self.old_shape()
        filled_pk, expected_creation = seeded['filled']
        own_pk, expected_own = seeded['own_moment']
        empty_pk, expected_nothing = seeded['without_log']

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        moments = self.moments(self.migrate_from)
        self.assertEqual(moments.get(filled_pk), expected_creation)
        self.assertEqual(moments.get(own_pk), expected_own)
        self.assertIsNone(moments.get(empty_pk))

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
