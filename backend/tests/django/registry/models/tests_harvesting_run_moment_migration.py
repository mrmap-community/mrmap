"""Fills the moment a run was made for the runs a deployment already has.

The fill of #1079 gave ``ProcessingData.date_created`` the ``default=now`` its
sibling in ``notify/models.py`` already has and, beside the two field states,
the ``UPDATE`` which fills the runs a deployment already has from the earliest
row of their change log. The rebuilt chain of #1850 answers that column with
the default from the first revision on and has no node at which the column
still stood empty, so there is no name of a revision left to travel between.
What this class proves has survived that: it builds the shape a deployment had
before the fill -- runs whose column answers nothing -- over the final schema,
and runs the very statement of the fill over them, in both directions: the
moments which the change log of the deployment knows, and the way back which
leaves them alone.
"""
from datetime import datetime, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.utils.timezone import now

from registry.models.harvest import HarvestingJob

#: the moments of the seeded change log, in the order of a deployment's own history
CREATED = datetime(2023, 3, 14, 7, 30, 12, 451223, tzinfo=timezone.utc)
PROGRESSED = datetime(2023, 3, 14, 7, 34, 5, 917004, tzinfo=timezone.utc)
OWN_MOMENT = datetime(2024, 11, 2, 16, 45, 0, 128003, tzinfo=timezone.utc)
ALREADY_LOGGED = datetime(2024, 11, 2, 16, 44, 58, 405990, tzinfo=timezone.utc)

#: the creation of every run whose own column is still empty, read from the
#: earliest revision of its change log -- the statement of the fill, carried
#: here verbatim from the node of the old chain which ran it. One statement,
#: because a deployment which harvested for years has thousands of runs and one
#: ``UPDATE`` per row would be thousands of statements. ``history_id`` breaks a
#: tie between revisions written in the same moment, as ``harvest_durations()``
#: orders it; a run whose change log is gone keeps its empty value and is not
#: given an invented date.
CREATION_FROM_CHANGE_LOG = """
    UPDATE registry_harvestingjob job
       SET date_created = made.history_date
      FROM (SELECT DISTINCT ON (history_relation_id)
                   history_relation_id,
                   history_date
              FROM registry_historicalharvestingjob
             ORDER BY history_relation_id, history_date, history_id) made
     WHERE job.date_created IS NULL
       AND made.history_relation_id = job.id
"""


class HarvestingRunMomentMigrationTest(TestCase):
    """What the fill writes from the change log and what its way back keeps.

    ``TransactionTestCase`` was needed while this class rolled the migration
    executor back over the fill node of the old chain; nothing migrates any
    more -- the shape before the fill is plain sql inside the transaction of
    the test, which postgres rolls back with it.
    """

    #: the migration of the rebuilt chain which creates the schema the fill
    #: runs on; the plan around it is what the tests run on
    INITIAL = ('registry', '0001_initial')

    def rebuilt_chain(self):
        """The plan of the rebuilt chain, which the fill runs on."""
        plan = MigrationExecutor(connection).loader.graph.forwards_plan(
            self.INITIAL)
        self.assertIn(self.INITIAL, plan)
        return plan

    def chain_column_the_fill_fills(self):
        """The column of the rebuilt chain which the fill fills.

        Read off the migrated test database, which is what ``0001_initial``
        answered: nullable -- a run whose creation cannot be known has to stay
        markable as unknown -- and without a default of the database. The
        moment of a new run is answered by the default of the FIELD, which is
        what the fill gave it and which the chain carries from its first
        revision on; the rows a deployment already had answered nothing on
        their own until the fill spoke for them, and that is the shape this
        class rebuilds below.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT is_nullable, column_default FROM information_schema.columns'
                ' WHERE table_name = %s AND column_name = %s',
                [HarvestingJob._meta.db_table, 'date_created'])
            row = cursor.fetchone()
        self.assertIsNotNone(
            row, 'the rebuilt chain does not answer the column of the run')
        nullable, column_default = row
        self.assertEqual(
            nullable, 'YES',
            'the rebuilt chain took the unknown out of the column which '
            '#1079 left markable as unknown')
        self.assertIsNone(
            column_default,
            'the rebuilt chain gave the column a default of the database '
            'behind the back of the fill - the rows a deployment already '
            'had would answer a moment nobody derived')
        self.assertIs(
            HarvestingJob._meta.get_field('date_created').default,
            now,
            'the field of the rebuilt chain does not answer the creation of '
            'its own - the default the fill gave is gone')

    def seed_run(self, **kwargs):
        """One run as a deployment wrote it, without a revision of its own.

        ``skip_history_when_saving`` is the seam with which this codebase
        writes a row without writing a revision of it: the change log of these
        runs is what ``old_shape`` writes and not what the test's own writes
        invent beside it.
        """
        job = HarvestingJob(**kwargs)
        job.skip_history_when_saving = True
        job.save()
        # which branch of the model's save() ran decides whether the seam is
        # still on the instance when it returns - it is set for the whole save
        # either way, which is what skips the revision
        if hasattr(job, 'skip_history_when_saving'):
            del job.skip_history_when_saving
        return job

    def revision(self, job, moment):
        """One row of a change log, as simple_history writes it for a save

        The change log mirrors the id of the run it describes in its own
        ``id``, so that is handed over; ``history_id`` is a uuid and answers
        its own default.
        """
        ChangeLog = HarvestingJob.change_log.model
        return ChangeLog.objects.create(
            id=job.pk, history_relation_id=job.pk,
            history_date=moment, history_type='+')

    def old_shape(self):
        """Runs of a deployment which harvested before the fill existed

        The rows carry the shape the column answered before the fill - every
        value in it written by hand, the runs the fill has to speak about
        still empty, which is what a deployment whose field never answered a
        default had:

        * a run whose change log names its creation and a later revision - the
          fill has to pick the earliest row and not the newest one of the log;
        * a run whose revisions were written newest first, which pins that
          "earliest" is read from the moment of a row and not from the order
          the rows went in;
        * a run which already answered a moment of its own while its change
          log names an earlier one - a column which holds a value is not
          overwritten by a derived guess;
        * a run whose change log is gone (revisions are pruned, and a row can
          predate the audit trail) - it keeps the empty value instead of being
          given an invented date.

        Returns:
            dict: the primary key of every seeded run beside the moment it has
                to answer afterwards, and the number of change log rows the
                seed wrote
        """
        filled = self.seed_run()
        self.revision(filled, CREATED)
        self.revision(filled, PROGRESSED)

        earliest_last = self.seed_run()
        self.revision(earliest_last, PROGRESSED)
        self.revision(earliest_last, CREATED)

        own_moment = self.seed_run(date_created=OWN_MOMENT)
        self.revision(own_moment, ALREADY_LOGGED)

        without_log = self.seed_run()

        # the runs the fill has to speak about: their column is still empty,
        # as it stood in a deployment whose field never answered a default
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE "%s" SET "date_created" = NULL WHERE "id" IN (%%s, %%s, %%s)'
                % HarvestingJob._meta.db_table,
                [filled.pk, earliest_last.pk, without_log.pk])
        self.assertEqual(
            self.moments(),
            {filled.pk: None, earliest_last.pk: None,
             own_moment.pk: OWN_MOMENT, without_log.pk: None},
            'the shape before the fill did not come up: the column answered '
            'something the fill was not about to find')

        return {
            'filled': (filled.pk, CREATED),
            'earliest_last': (earliest_last.pk, CREATED),
            'own_moment': (own_moment.pk, OWN_MOMENT),
            'without_log': (without_log.pk, None),
            'revisions': self.revision_count(),
        }

    def moments(self):
        """The moment every run answers, read from the database

        Returns:
            dict: per run id the moment its column answers
        """
        return dict(HarvestingJob.objects.values_list('pk', 'date_created'))

    def revision_count(self):
        """The rows of the change log under the schema the fill leaves behind"""
        return HarvestingJob.change_log.model.objects.count()

    def fill(self):
        """The upgrade itself: the statement of the fill over the rows

        The two field states of the node changed nothing of the schema -- the
        column was there all along, only its field answered nothing -- so what
        the upgrade did to the rows of a deployment is this statement and
        nothing else.
        """
        with connection.cursor() as cursor:
            cursor.execute(CREATION_FROM_CHANGE_LOG)

    def test_forwards_fills_the_runs_the_change_log_knows(self):
        """Every run whose own change log records its creation answers that
        moment afterwards, a run which already answered a moment keeps it, and
        a run without a change log stays empty (#1079: the list of runs of
        #1087 orders the old runs below the new ones only once the column
        holds the moment a deployment already has somewhere else)"""
        self.rebuilt_chain()
        self.chain_column_the_fill_fills()
        seeded = self.old_shape()
        filled_pk, expected_creation = seeded['filled']
        earliest_pk, expected_earliest = seeded['earliest_last']
        own_pk, expected_own = seeded['own_moment']
        empty_pk = seeded['without_log'][0]

        self.fill()

        moments = self.moments()
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
            "the fill wrote a revision of its own - the moment it fills is read "
            "from the change log, it does not belong in it")
        fresh = self.seed_run()
        self.assertIsNotNone(
            self.moments().get(fresh.pk),
            "a run which a filled deployment creates answers no creation of its "
            "own - the default the fill gave the field is gone")

    def test_backwards_keeps_the_recovered_moments(self):
        """The reverse of the fill is nothing on purpose: the moments it wrote
        came out of the change log of the deployment and stay true after a
        downgrade, so a rollback does not throw away what the upgrade
        recovered. Nothing of the column goes back either -- it never answered
        anything on the database level which the downgrade could take away --
        so an older version reads the same runs it wrote before"""
        self.rebuilt_chain()
        seeded = self.old_shape()
        filled_pk, expected_creation = seeded['filled']
        own_pk, expected_own = seeded['own_moment']
        empty_pk = seeded['without_log'][0]

        self.fill()
        recovered = self.moments()

        # The way back runs nothing over these rows -- that is what the node
        # declared and what this asks: the moments came out of the change log
        # and remain true below the fill.
        moments = self.moments()
        self.assertEqual(
            moments, recovered,
            "the way back changed a moment the fill had recovered")
        self.assertEqual(moments.get(filled_pk), expected_creation)
        self.assertEqual(moments.get(own_pk), expected_own)
        self.assertIsNone(moments.get(empty_pk))
