"""The liveness evidence of the conformity task family (#1394).

The audit of #1388 classified ``run_conformity_check`` and its two workers
"not enough evidence" and told #1394 to establish whether the family is
wired before any optimization verdict - and the regression matrix of #1395
(``celery-task-sql-regression``) deliberately pins no query guard for it
while that question stands. The answer established here:

*   nothing on develop dispatches ``async_run_conformity_check`` - no view,
    serializer, model hook, beat row or ``send_task`` names it, and nothing
    in the frontend asks for conformity (grepped on the PR of #1394); the
    tasks are registered and reachable by name only;
*   the tasks could not answer even that by-name delivery: they read
    ``ConformityCheckRun.objects``, which is the ABSTRACT base of four
    sibling concrete tables - the read below targets a relation the
    migration history never created.

So the family is dead code, not a candidate for query work: #1394 retired
the ``self.task``/``self.job`` writes of the removed django-celery-results
store (#1178/#1180) and left the keep-or-remove decision of the whole
family to its owners, reported on the issue. These tests are the durable
evidence: should the family be revived, the guard fails and forces the
re-review of its SQL.
"""
import ast
import inspect

from django.db import connection
from django.test import TestCase

import registry.tasks.conformity as conformity_tasks
from registry.models.conformity import ConformityCheckRun


class ConformityFamilyLivenessTest(TestCase):
    """what the by-name-only tasks would hit if anyone delivered one"""

    def test_the_abstract_base_read_of_the_tasks_can_never_answer(self):
        """``ConformityCheckRun`` is abstract: its base table does not exist.

        The task bodies of ``registry/tasks/conformity.py`` fetch the run
        through ``ConformityCheckRun.objects``; the four concrete run
        tables each hold their own rows and a pk alone does not say which
        one to read, so no delivery can complete this fetch.
        """
        self.assertTrue(ConformityCheckRun._meta.abstract)
        self.assertNotIn(
            ConformityCheckRun._meta.db_table,
            connection.introspection.table_names(),
            'the base read of the conformity tasks names a table the '
            'migration history never created')
        with self.assertRaises(Exception):
            list(ConformityCheckRun.objects.all())

    def test_the_result_backend_seam_stays_retired(self):
        """The removed DB result store (#1178/#1180) must not creep back.

        ``self.task``/``self.job`` never resolve on today's Celery: the
        status/progress/phase writes were statements against the retired
        django-celery-results table and can only raise since the result
        backend became Redis. #1394 deleted them; this guard keeps the
        family free of that seam until its owners decide its fate.

        The check reads the CODE, not the text: the module documents the
        retired seam by name and still must not use it, so the assertion
        walks the syntax tree for ``self.task``/``self.job`` attribute
        reads and for a ``bind=True`` task (the only way a module function
        ever gets a ``self``).
        """
        tree = ast.parse(inspect.getsource(conformity_tasks))
        seams = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and node.attr in ('task', 'job')
                    and isinstance(node.value, ast.Name)
                    and node.value.id == 'self'):
                seams.append(f'self.{node.attr}')
            elif isinstance(node, ast.Call) and any(
                    keyword.arg == 'bind' for keyword in node.keywords):
                seams.append('bind=True')
        self.assertEqual(
            seams, [],
            'the retired task-result-store seam '
            f'{sorted(set(seams))} is back in the conformity tasks '
            '(#1178/#1180 removed that backend)')
