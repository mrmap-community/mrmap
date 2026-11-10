"""Carries the task ids the retired relation still evidences (#1180).

The schema work of this node is empty and its name is load-bearing twice over:
every database of the release which carries #1179 applied the real ``RemoveField``
under this name, and ``0007_backgroundprocess_action_required_and_more`` of #1229
parents on this node. The field is gone from the model state, so the node cannot
declare the ``RemoveField`` again; what it does instead is the data step D03 of
#1175 asked for before that table goes.

What it carries
    ``notify_backgroundprocess_threads`` was the association between a process and
    the celery ``TaskResult`` rows of its work. Wherever it still exists, the task
    ids it names are unioned into ``BackgroundProcess.celery_task_ids`` - the
    column cancellation reads (#1179) - and the table is then dropped. An
    association which is not carried is an association nobody can revoke after the
    upgrade.

Why the step is guarded and self-skipping
    **The premise of D03 was overtaken before this node could be written.** #1179
    merged as ``notify/0006`` on 2026-11-10 and dropped the many-to-many relation
    then, and a ``RemoveField`` of an ``M2M`` drops its through table. Every
    database which migrated to that revision - which is the supported baseline of
    this release - therefore arrives with the table already gone, and an audit of
    the production paths which came with #1179 found no code populating the
    relation, so the set of associations to carry is expected to be empty. That is
    the expected case, not a failure, and the step says which way it went in the
    log instead of pretending to have found nothing. A deployment which reaches
    this chain *without* having applied #1179 is exactly the one the guard still
    serves.

What is deliberately not mapped
    No outcome is read out of a legacy row. A ``TaskResult`` row is one task, and a
    ``BackgroundProcess`` is the aggregate of several, so a terminal row says
    nothing reliable about the aggregate; and a row which never left ``PENDING``
    (or ``RECEIVED``/``STARTED``/``RETRY``/``REJECTED``) says nothing about its task
    either. D03: unknown stays unknown, and nothing here writes completed, failed
    or aborted anywhere.

Why this is not reversible
    A carried id cannot be told apart from one the application registered itself,
    and a dropped table is not rebuilt from the current state. The reverses are
    therefore ``noop``, which is also why the release before this one rolls back
    onto the same database only as long as #1179 was applied there.
"""
import logging
import re
import uuid

from django.db import migrations

#: the through table of the retired ``threads`` relation, named by the database
#: because no model of this app owns it any more
THROUGH_TABLE = 'notify_backgroundprocess_threads'

#: the table of the package this release uninstalls, still readable at this
#: moment: it is where the ``task_id`` of an association row lives
LEGACY_TASKRESULT_TABLE = 'django_celery_results_taskresult'

#: celery ids are uuid4 texts, and the column which receives them is an array of
#: uuids; a text which is not one has nowhere to go and is reported, not guessed
UUID_TEXT = re.compile(
    r'^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')


def evidenced_associations(connection):
    """The (process pk, task id) pairs the relation still evidences.

    Returns ``None`` when there is no through table to read, which is the
    self-skip, and an empty list when the association survives without its
    counterpart table - a database which uninstalled the package behind its own
    back, whose associations name no task id that could be read.
    """
    tables = connection.introspection.table_names()
    if THROUGH_TABLE not in tables:
        return None
    if LEGACY_TASKRESULT_TABLE not in tables:
        logging.warning(
            'notify.0006: %s is there but %s is not, so no association of it '
            'names a task id which could be carried',
            THROUGH_TABLE, LEGACY_TASKRESULT_TABLE)
        return []
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT th.backgroundprocess_id, tr.task_id '
            'FROM %s th JOIN %s tr ON tr.id = th.taskresult_id '
            'ORDER BY th.id' % (quote(THROUGH_TABLE),
                                quote(LEGACY_TASKRESULT_TABLE)))
        # one row per association of an opted-in task, so the whole set is read
        # at once rather than one query per process
        return list(cursor.fetchall())


def union_evidenced_task_ids(apps, schema_editor):
    """Union the evidenced ids into the array cancellation reads (#1175/D03).

    Written with ``update`` on the historical model, not ``save``: the process
    must not run the lifecycle of the model it is stored in while that model is
    being migrated.
    """
    connection = schema_editor.connection
    associations = evidenced_associations(connection)
    if associations is None:
        logging.info(
            'notify.0006: no %s to read - the relation was already retired here '
            'by notify/0006 of #1179, which is the expected case for a '
            'deployment on the supported baseline', THROUGH_TABLE)
        return

    evidenced = {}
    unreadable = 0
    for process_pk, task_id in associations:
        if not UUID_TEXT.match(task_id or ''):
            unreadable += 1
            continue
        evidenced.setdefault(process_pk, []).append(uuid.UUID(task_id))

    BackgroundProcess = apps.get_model('notify', 'BackgroundProcess')
    processes = BackgroundProcess.objects.using(connection.alias)
    carried = 0
    for process_pk, task_ids in evidenced.items():
        current = processes.filter(pk=process_pk).values_list(
            'celery_task_ids', flat=True).first()
        if current is None:
            # the process is gone; its association goes with it
            continue
        known = {str(task_id) for task_id in current}
        merged = list(current) + [
            task_id for task_id in task_ids if str(task_id) not in known]
        if merged == list(current):
            continue
        processes.filter(pk=process_pk).update(celery_task_ids=merged)
        carried += 1

    logging.info(
        'notify.0006: carried the evidenced task ids of %d of %d processes '
        'named by %s (%d associations of %d read here name a task id which is '
        'no uuid text and cannot be stored in the array)',
        carried, len(evidenced), THROUGH_TABLE, unreadable, len(associations))


def drop_retired_through_table(apps, schema_editor):
    """Remove the through table of a relation no model of this app declares.

    ``IF EXISTS`` of its own is not enough to be honest about the guard, so the
    catalog is asked first: the table is absent both on a new installation, which
    never had the relation, and on a database which applied #1179.
    """
    connection = schema_editor.connection
    if THROUGH_TABLE not in connection.introspection.table_names():
        return
    with connection.cursor() as cursor:
        cursor.execute('DROP TABLE %s'
                       % connection.ops.quote_name(THROUGH_TABLE))


class Migration(migrations.Migration):

    dependencies = [
        ('notify', '0005_alter_backgroundprocess_process_type'),
    ]

    operations = [
        migrations.RunPython(
            union_evidenced_task_ids, migrations.RunPython.noop),
        migrations.RunPython(
            drop_retired_through_table, migrations.RunPython.noop),
    ]
