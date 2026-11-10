"""What ``notify/0006`` carries across the removal of the retired relation.

D03 of #1175, as accepted on #1180: where the through table of the retired
``threads`` relation still exists, the task ids it evidences belong to
``BackgroundProcess.celery_task_ids`` - the array cancellation reads since #1179 -
and the outcome of every task whose state is a fact of its own row belongs in the
logs of that process, before the table goes. An association which is not carried
is an association nobody can revoke after the upgrade; an outcome which is not
carried is a history nobody can read after the uninstall.

The node's own functions are called directly here, instead of travelling a
``MigrationExecutor`` between two nodes as the registry's task-id migration test
does: the regenerated history cannot produce the old shape for an executor to
travel from, because ``0001_initial`` never creates the relation (#1180). A test
database therefore has no through table to be rolled back to, so the test creates
the tables as the migration finds them and asks both guards - the database which
still has the table, and the one which applied #1179 and has none.
"""
import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.utils import timezone

from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog

#: the node under test; a migration module is not reachable by a ``from`` clause
migration = importlib.import_module(
    'notify.migrations.0006_remove_backgroundprocess_threads')

#: a fixed moment, so that the date a carried log quotes can be asserted and is
#: not the time the test happened to run
RECORDED = timezone.make_aware(datetime(2026, 11, 9, 8, 0))

#: the table of the package this release uninstalls: only the columns the step
#: reads are declared, which is what the join of the step may name
LEGACY_TASKRESULT = """
    CREATE TABLE django_celery_results_taskresult (
        id bigserial PRIMARY KEY,
        task_id varchar(255) NOT NULL UNIQUE,
        status varchar(50) NOT NULL DEFAULT 'PENDING',
        date_done timestamptz NULL,
        date_created timestamptz NULL
    )
"""

#: the same, of the shape a long lived deployment can still have: a table which
#: predates the date columns the step would like to read
LEGACY_TASKRESULT_UNDATED = """
    CREATE TABLE django_celery_results_taskresult (
        id bigserial PRIMARY KEY,
        task_id varchar(255) NOT NULL UNIQUE,
        status varchar(50) NOT NULL DEFAULT 'PENDING'
    )
"""

#: the through table as it stood under the many-to-many. Of its own constraints
#: nothing is reproduced: the step reads two columns and the case which has to
#: survive is an association whose process is no longer there, which a cascading
#: foreign key of the real table would have removed before the migration saw it
THROUGH_TABLE = """
    CREATE TABLE notify_backgroundprocess_threads (
        id bigserial PRIMARY KEY,
        backgroundprocess_id bigint NOT NULL,
        taskresult_id bigint NOT NULL
    )
"""


class CarryTheEvidencedTaskResultsTest(TestCase):
    """The carry-over of ``0006``, its guards, and what it must leave alone.

    ``TestCase`` and not ``TransactionTestCase``: the tables this test creates
    and drops are DDL inside the transaction of the test, so the schema of the
    database is found as it was whatever order the tests run in.
    """

    def setUp(self):
        super().setUp()
        # the model state the node sees, which is what RunPython is handed
        self.apps = MigrationLoader(connection).project_state(
            [('notify', '0006_remove_backgroundprocess_threads')]).apps
        # RunPython hands a data step its schema editor, of which the step reads
        # the connection and nothing else
        self.editor = SimpleNamespace(connection=connection)
        # whether the legacy table of the case being built holds date columns
        self.dated = True

    # -- the shape the migration finds ----------------------------------------

    def legacy_tables(self, dated=True):
        with connection.cursor() as cursor:
            cursor.execute(LEGACY_TASKRESULT if dated
                           else LEGACY_TASKRESULT_UNDATED)
            cursor.execute(THROUGH_TABLE)
        self.dated = dated

    def associate(self, process_pk, *task_rows):
        """Link a process to legacy rows, in the order in which they are given

        Args:
            process_pk: the process to name, existing or not
            task_rows: ``(task id, celery state, date done, date created)``
                tuples, of which the two dates may be left out; a ``None`` date
                done is the case of a task which never finished
        """
        with connection.cursor() as cursor:
            for row in task_rows:
                task_id, status = row[0], row[1]
                date_done = row[2] if len(row) > 2 else RECORDED
                date_created = row[3] if len(row) > 3 else RECORDED
                if self.dated:
                    cursor.execute(
                        "INSERT INTO django_celery_results_taskresult "
                        "(task_id, status, date_done, date_created) "
                        "VALUES (%s, %s, %s, %s) RETURNING id",
                        [task_id, status, date_done, date_created])
                else:
                    cursor.execute(
                        "INSERT INTO django_celery_results_taskresult "
                        "(task_id, status) VALUES (%s, %s) RETURNING id",
                        [task_id, status])
                cursor.execute(
                    "INSERT INTO notify_backgroundprocess_threads "
                    "(backgroundprocess_id, taskresult_id) VALUES (%s, %s)",
                    [process_pk, cursor.fetchone()[0]])

    def carry(self):
        migration.carry_evidenced_task_results(self.apps, self.editor)

    def carried_ids(self, process):
        """The array as the live model answers it, so the read side is tested"""
        return sorted(
            str(task_id) for task_id in
            BackgroundProcess.objects.get(pk=process.pk).celery_task_ids)

    def logs_of(self, process):
        """The logs of the process, oldest first, as the application reads them"""
        return list(BackgroundProcessLog.objects
                    .filter(background_process=process).order_by('id'))

    def process(self, **kwargs):
        kwargs.setdefault(
            'description', 'a process with work behind the relation')
        return BackgroundProcess.objects.create(
            phase='collecting', process_type='registering', **kwargs)

    # -- what is carried ------------------------------------------------------

    def test_the_ids_an_association_evidences_join_the_array(self):
        """The ids behind the relation are owned afterwards, none of them twice.

        The root id is registered the way #1179 registers it and is also behind
        an association, so the carry-over has to keep it exactly once; the second
        id arrives only through the association and is the one which would be
        lost.
        """
        self.legacy_tables()
        root, evidenced = uuid4(), uuid4()
        process = self.process(celery_task_ids=[root])
        self.associate(process.pk, (str(evidenced), 'SUCCESS'),
                       (str(root), 'SUCCESS'))

        self.carry()

        self.assertEqual(
            self.carried_ids(process), sorted([str(root), str(evidenced)]),
            'the association did not reach the array, or it reached it twice')

    def test_a_terminal_state_of_a_task_becomes_a_log_of_its_process(self):
        """The outcome of one task is a fact of its row, so it is kept (#1180/4)

        The three states of ``TERMINAL_TASK_STATES`` are mapped, each with the
        date the backend recorded and with the marker which names where the row
        came from, because an operator has to be able to tell a carried line from
        one the application logged.
        """
        self.legacy_tables()
        revoked, succeeded, failed = uuid4(), uuid4(), uuid4()
        process = self.process()
        self.associate(process.pk,
                       (str(revoked), 'REVOKED', RECORDED),
                       (str(succeeded), 'SUCCESS', None,
                        RECORDED + timedelta(minutes=5)),
                       (str(failed), 'FAILURE',
                        RECORDED + timedelta(hours=2)))

        self.carry()

        logs = self.logs_of(process)
        self.assertEqual(
            [(log.log_type, log.date) for log in logs],
            [('error', RECORDED),
             ('info', RECORDED + timedelta(minutes=5)),
             ('error', RECORDED + timedelta(hours=2))],
            'the state which never finished is dated by the creation the backend '
            'recorded, every other one by the moment it answered for')
        self.assertEqual(
            [word in log.description for log, word in
             zip(logs, ('revoked', 'completed', 'failed'))],
            [True, True, True],
            'a carried log has to name the state it was read out of')
        self.assertEqual(len(self.carried_ids(process)), 3,
                         'all three ids are owned by the process afterwards')
        for log in logs:
            self.assertTrue(
                log.description.startswith(migration.CARRIED_MARKER),
                'a carried row which cannot be recognised as one is a carried '
                'row nobody can undo')

    def test_the_state_of_the_process_is_never_read_out_of_a_task_row(self):
        """A terminal row of one task says nothing about the aggregate (#1175/D03)

        Three tasks of one process are in three states, one of them terminal and
        one which never left ``PENDING``; none of it may answer a state of the
        process, which stays as it was.
        """
        self.legacy_tables()
        process = self.process()
        self.associate(process.pk, (str(uuid4()), 'SUCCESS'),
                       (str(uuid4()), 'FAILURE'), (str(uuid4()), 'PENDING'))

        self.carry()

        stored = BackgroundProcess.objects.get(pk=process.pk)
        self.assertEqual(stored.status, ProcessStatusEnum.PENDING)
        self.assertIsNone(stored.done_at)
        self.assertEqual(len(self.carried_ids(process)), 3,
                         'the ids were carried, which is all this step may do '
                         'to the process itself')

    def test_no_log_is_written_for_a_state_which_is_no_outcome_of_its_own(self):
        """Unknown stays unknown, which is the safeguard of #1180 answer 4

        Every state the retired backend could leave a task in without a result,
        plus a state which is none of its states at all, may not become a line in
        the logs: a deployment reading the logs afterwards has to be able to trust
        each of them.
        """
        self.legacy_tables()
        states = ('PENDING', 'RECEIVED', 'STARTED', 'RETRY', 'REJECTED',
                  'IGNORED', 'ACKNOWLEDGED', 'nonsense', '')
        process = self.process()
        rows = [(str(uuid4()), state) for state in states]
        self.associate(process.pk, *rows)

        self.carry()

        self.assertEqual(self.logs_of(process), [],
                         'a state which records no result of its own may not '
                         'be read as one')
        self.assertEqual(len(self.carried_ids(process)), len(states),
                         'the associations are still carried: an unknown '
                         'outcome is not an unknown owner')

    def test_the_case_of_a_task_id_which_is_no_uuid_text(self):
        """The array receives uuids, so a foreign id stays out - its outcome not

        A deployment which set its own task ids would otherwise fail the upgrade
        on a cast, and an id cannot be guessed into a uuid it is not. But the
        state its row records is as verifiable as that of any other task, so the
        log is written and names the id as it stands.
        """
        self.legacy_tables()
        process = self.process()
        self.associate(process.pk,
                       ('first-delivery-of-the-2024-import', 'FAILURE'))

        self.carry()

        self.assertEqual(self.carried_ids(process), [])
        logs = self.logs_of(process)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].log_type, LogTypeEnum.ERROR)
        self.assertIn('first-delivery-of-the-2024-import',
                      logs[0].description)

    def test_an_association_without_its_process_is_left_behind(self):
        """Nothing of a process which is gone is carried to nowhere

        The row of the process is removed by the database and not of the model,
        which is how a deployment can hold an association whose process a cleaner
        already deleted.
        """
        self.legacy_tables()
        process = self.process()
        self.associate(process.pk, (str(uuid4()), 'SUCCESS'))
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM notify_backgroundprocess WHERE id = %s',
                           [process.pk])

        self.carry()

        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM notify_backgroundprocess')
            self.assertEqual(cursor.fetchone()[0], 0)
        self.assertEqual(
            BackgroundProcessLog.objects.count(), 0,
            'a log of a process which is gone is a log nobody will ever read')

    def test_a_legacy_table_without_the_date_columns_is_still_read(self):
        """A table which predates the dates loses its dates, not its history

        The step asks the catalog which columns there are, because a migration
        which failed on a missing column would carry nothing at all - and the log
        it writes then says plainly that no date was recorded instead of inventing
        one.
        """
        self.legacy_tables(dated=False)
        process = self.process()
        self.associate(process.pk, (str(uuid4()), 'SUCCESS'))

        self.carry()

        self.assertEqual(len(self.carried_ids(process)), 1)
        logs = self.logs_of(process)
        self.assertEqual(len(logs), 1)
        self.assertIn('did not record', logs[0].description)

    # -- the guards -----------------------------------------------------------

    def test_a_new_database_never_creates_the_legacy_tables(self):
        """A clean installation of this release has nothing to export (#1180)

        The test database is built by running the regenerated history from
        scratch, so it is the clean installation the operator documentation
        promises: neither the through table of the retired relation nor a single
        table of the uninstalled package is created by it.
        """
        tables = connection.introspection.table_names()
        self.assertNotIn(migration.THROUGH_TABLE, tables)
        for table in tables:
            self.assertFalse(
                table.startswith('django_celery_results_'),
                f'{table} was created by a history which no longer names the '
                f'package')

    def test_the_step_skips_where_the_relation_is_already_retired(self):
        """The supported baseline: #1179 dropped the table, so there is nothing

        Not a failure and not a warning: this is the case every deployment on the
        baseline of this release arrives with.
        """
        process = self.process(description='a process of the supported baseline')

        self.assertIsNone(
            migration.evidenced_tasks(connection),
            'the guard is expected to answer that there is nothing to read, '
            'which is what tells the step to skip instead of failing')
        self.carry()
        migration.drop_retired_through_table(self.apps, self.editor)

        self.assertEqual(self.carried_ids(process), [])
        self.assertEqual(self.logs_of(process), [])

    def test_the_through_table_goes_and_its_removal_is_safe_to_ask_twice(self):
        """The table of a relation no model of this app declares is removed"""
        self.legacy_tables()

        migration.drop_retired_through_table(self.apps, self.editor)
        self.assertNotIn(
            migration.THROUGH_TABLE, connection.introspection.table_names())
        # and a new installation, which never had it, is not asked to drop it
        migration.drop_retired_through_table(self.apps, self.editor)

    def test_the_history_keeps_the_name_and_needs_no_third_party_app(self):
        """The node stays reachable for #1229 and nothing of notify names the
        uninstalled package any more (#1180)"""
        graph = MigrationLoader(connection).graph
        self.assertIn(
            ('notify', '0006_remove_backgroundprocess_threads'), graph.nodes,
            '0006 is the parent of 0007_backgroundprocess_action_required_'
            'and_more of #1229 and of every applied record of the baseline')
        for node in [n for n in graph.nodes if n[0] == 'notify']:
            for parent in graph.node_map[node].parents:
                self.assertNotEqual(
                    parent[0], 'django_celery_results',
                    f'{node} still depends on the uninstalled app')
