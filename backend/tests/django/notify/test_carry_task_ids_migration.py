"""What ``notify/0006`` carries across the removal of the retired relation.

D03 of #1175, as accepted on #1180: where the through table of the retired
``threads`` relation still exists, the task ids it evidences belong to
``BackgroundProcess.celery_task_ids`` - the array cancellation reads since #1179 -
before that table goes. An association which is not carried is an association
nobody can revoke after the upgrade.

The node's own functions are called directly here, instead of travelling a
``MigrationExecutor`` between two nodes as the registry's task-id migration test
does: the regenerated history cannot produce the old shape for an executor to
travel from, because ``0001_initial`` never creates the relation (#1180). A test
database therefore has no through table to be rolled back to, so the test creates
the tables as the migration finds them and asks both guards - the database which
still has the table, and the one which applied #1179 and has none.
"""
import importlib
from types import SimpleNamespace
from uuid import uuid4

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess

#: the node under test; a migration module is not reachable by a ``from`` clause
migration = importlib.import_module(
    'notify.migrations.0006_remove_backgroundprocess_threads')

#: the table of the package this release uninstalls: only the two columns the
#: step reads are declared, which is what the join of the step may name
LEGACY_TASKRESULT = """
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


class CarryTheEvidencedTaskIdsTest(TestCase):
    """The union of ``0006``, its two guards, and what it must leave alone.

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

    # -- the shape the migration finds ----------------------------------------

    def legacy_tables(self):
        with connection.cursor() as cursor:
            cursor.execute(LEGACY_TASKRESULT)
            cursor.execute(THROUGH_TABLE)

    def associate(self, process_pk, *task_rows):
        """Link a process to legacy rows, in the order in which they are given

        Args:
            process_pk: the process to name, existing or not
            task_rows: (task id text, celery state) pairs to insert and link
        """
        with connection.cursor() as cursor:
            for task_id, status in task_rows:
                cursor.execute(
                    "INSERT INTO django_celery_results_taskresult "
                    "(task_id, status) VALUES (%s, %s) RETURNING id",
                    [task_id, status])
                cursor.execute(
                    "INSERT INTO notify_backgroundprocess_threads "
                    "(backgroundprocess_id, taskresult_id) VALUES (%s, %s)",
                    [process_pk, cursor.fetchone()[0]])

    def union(self):
        migration.union_evidenced_task_ids(self.apps, self.editor)

    def carried_ids(self, process):
        """The array as the live model answers it, so the read side is tested"""
        return sorted(
            str(task_id) for task_id in
            BackgroundProcess.objects.get(pk=process.pk).celery_task_ids)

    # -- what is carried ------------------------------------------------------

    def test_the_ids_an_association_evidences_join_the_array(self):
        """The ids behind the relation are owned afterwards, none of them twice.

        The root id is registered the way #1179 registers it and is also behind
        an association, so the union has to keep it exactly once; the second id
        arrives only through the association and is the one which would be lost.
        """
        self.legacy_tables()
        root, evidenced = uuid4(), uuid4()
        process = BackgroundProcess.objects.create(
            phase='collecting', process_type='registering',
            description='a registration with work behind the relation',
            celery_task_ids=[root])
        self.associate(process.pk, (str(evidenced), 'SUCCESS'),
                       (str(root), 'SUCCESS'))

        self.union()

        self.assertEqual(
            self.carried_ids(process), sorted([str(root), str(evidenced)]),
            'the association did not reach the array, or it reached it twice')

    def test_an_association_without_its_process_is_left_behind(self):
        """An id of a process which is gone has nowhere to be carried to

        The row of the process is removed by the database and not of the model,
        which is how a deployment can hold an association whose process a cleaner
        already deleted.
        """
        self.legacy_tables()
        process = BackgroundProcess.objects.create(
            phase='collecting', process_type='registering',
            description='a process which does not outlive its association')
        self.associate(process.pk, (str(uuid4()), 'SUCCESS'))
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM notify_backgroundprocess WHERE id = %s',
                           [process.pk])

        self.union()

        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM notify_backgroundprocess')
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_a_task_id_which_is_no_uuid_text_is_not_carried(self):
        """The column receives uuids, so a text which is not one is passed over

        A deployment which set its own task ids would otherwise fail the upgrade
        on a cast, and an id cannot be guessed into a uuid it is not.
        """
        self.legacy_tables()
        process = BackgroundProcess.objects.create(
            phase='collecting', process_type='registering',
            description='a deployment with hand written task ids')
        self.associate(process.pk, ('first-delivery-of-the-2024-import',
                                    'SUCCESS'))

        self.union()

        self.assertEqual(self.carried_ids(process), [])

    def test_no_outcome_is_read_out_of_a_legacy_row(self):
        """A terminal row of one task says nothing about the aggregate (#1175/D03)

        Three tasks of one process are in three states, one of them terminal and
        one which never left ``PENDING``; none of it may answer a state of the
        process, which stays as it was.
        """
        self.legacy_tables()
        process = BackgroundProcess.objects.create(
            phase='collecting', process_type='registering',
            description='a process whose tasks are in three states')
        self.associate(process.pk, (str(uuid4()), 'SUCCESS'),
                       (str(uuid4()), 'FAILURE'), (str(uuid4()), 'PENDING'))

        self.union()

        stored = BackgroundProcess.objects.get(pk=process.pk)
        self.assertEqual(stored.status, ProcessStatusEnum.PENDING)
        self.assertIsNone(stored.done_at)
        self.assertEqual(len(self.carried_ids(process)), 3,
                         'the ids were carried, which is all this step may do')

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
        process = BackgroundProcess.objects.create(
            phase='collecting', process_type='registering',
            description='a process of the supported baseline')

        self.assertIsNone(
            migration.evidenced_associations(connection),
            'the guard is expected to answer that there is nothing to read, '
            'which is what tells the step to skip instead of failing')
        self.union()
        migration.drop_retired_through_table(self.apps, self.editor)

        self.assertEqual(self.carried_ids(process), [])

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
