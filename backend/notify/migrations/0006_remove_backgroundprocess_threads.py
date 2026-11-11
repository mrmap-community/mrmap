"""Carries what the retired relation still evidences (#1180).

The schema work of this node is empty and its name is load-bearing twice over:
every database of the release which carries #1179 applied the real ``RemoveField``
under this name, and ``0007_backgroundprocess_action_required_and_more`` of #1229
parents on this node. The field is gone from the model state, so the node cannot
declare the ``RemoveField`` again; what it does instead is the data step D03 of
#1175 asked for before that table goes.

What it carries
    ``notify_backgroundprocess_threads`` was the association between a process and
    the celery ``TaskResult`` rows of its work. Wherever it still exists, two
    things are read out of it and out of the rows it points at, and only then is
    the table dropped:

    * the task ids, unioned into ``BackgroundProcess.celery_task_ids`` - the
      column cancellation reads since #1179. An association which is not carried
      is an association nobody can revoke after the upgrade.
    * the outcome of every task which reached a state that is a fact of its own
      row, appended to the logs of the process as a ``BackgroundProcessLog``
      dated by the backend. This is the "preserve verifiable historical outcomes
      ... wherever reliably mappable" of #1180 answer 4, and the log is the only
      supported store of this app which can hold a statement about one past task:
      the results themselves went with #1178 to the Celery result backend, which
      is Redis and disposable.

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

What stays unknown
    The state of the *process* is never written here. A ``TaskResult`` row is one
    task and a ``BackgroundProcess`` is the aggregate of several, so no terminal
    row answers the aggregate, and nothing in this node touches ``status`` or
    ``done_at``. Of the per-task states, only the three of
    ``TERMINAL_TASK_STATES`` are read as an outcome: ``PENDING``, ``RECEIVED``,
    ``STARTED``, ``RETRY`` and ``REJECTED`` are the rows #1180 answer 4 names as
    never to invent an outcome for, so they produce no log row at all - unknown
    stays unknown rather than becoming a line an operator cannot tell apart from a
    real one.

Why this is not reversible
    A carried id cannot be told apart from one the application registered itself,
    and a dropped table is not rebuilt from the current state. The reverses are
    therefore ``noop``, which is also why the release before this one rolls back
    onto the same database only as long as #1179 was applied there. The log rows
    this node writes can at least be identified - every one of them begins with
    ``CARRIED_MARKER`` - so an operator who wants them gone can delete exactly
    those; the ids, once unioned, cannot.
"""
import logging
import re
import uuid

from django.db import migrations
from django.utils import timezone

#: the through table of the retired ``threads`` relation, named by the database
#: because no model of this app owns it any more
THROUGH_TABLE = 'notify_backgroundprocess_threads'

#: the table of the package this release uninstalls, still readable at this
#: moment: it is where the ``task_id`` and the state of an association live
LEGACY_TASKRESULT_TABLE = 'django_celery_results_taskresult'

#: celery ids are uuid4 texts, and the column which receives them is an array of
#: uuids; a text which is not one has nowhere to go and is reported, not guessed
UUID_TEXT = re.compile(
    r'^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')

#: the states which the retired backend wrote *for one task* and which are a fact
#: of that row, mapped onto the log type and the word an operator reads. It is
#: celery's own set of ready states minus ``REJECTED``, which #1180 answer 4
#: names as a state to read no outcome from. The types are the literals of
#: ``LogTypeEnum`` of ``notify/enums.py``: a data step speaks to the database
#: rather than importing the module it migrates, which also keeps this file
#: independent of code that may move later
TERMINAL_TASK_STATES = {
    'SUCCESS': ('info', 'completed'),
    'FAILURE': ('error', 'failed'),
    'REVOKED': ('error', 'revoked'),
}

#: written into every log row this step adds, so a carried outcome can be told
#: apart from one the application logged, and deleted on its own if an operator
#: decides the carry-over is not wanted
CARRIED_MARKER = ('[#1180 carried over from '
                  'django_celery_results_taskresult]')

#: the columns of the legacy table this node reads, in the order it reads them
EVIDENCED_COLUMNS = ('task_id', 'status', 'date_done', 'date_created')


def evidenced_tasks(connection):
    """The tasks the relation still evidences, as one list of tuples.

    Each entry is ``(process pk, task id, state, date done, date created)``.
    Returns ``None`` when there is no through table to read, which is the
    self-skip, and an empty list when the association survives without its
    counterpart table - a database which uninstalled the package behind its own
    back, whose associations name no task that could be read.

    The columns are asked of the catalog and left out when a table predates them:
    the ids of an association are worth carrying either way, and a migration
    which failed on a missing column would carry nothing at all.
    """
    tables = connection.introspection.table_names()
    if THROUGH_TABLE not in tables:
        return None
    if LEGACY_TASKRESULT_TABLE not in tables:
        logging.warning(
            'notify.0006: %s is there but %s is not, so no association of it '
            'names a task which could be carried',
            THROUGH_TABLE, LEGACY_TASKRESULT_TABLE)
        return []

    with connection.cursor() as cursor:
        have = {column.name for column in
                connection.introspection.get_table_description(
                    cursor, LEGACY_TASKRESULT_TABLE)}
    selected = [column for column in EVIDENCED_COLUMNS if column in have]
    if 'task_id' not in selected:
        logging.warning(
            'notify.0006: %s has no task_id column, so nothing of it names a '
            'task which could be carried', LEGACY_TASKRESULT_TABLE)
        return []

    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT th.backgroundprocess_id, %s FROM %s th '
            'JOIN %s tr ON tr.id = th.taskresult_id ORDER BY th.id'
            % (', '.join('tr.%s' % quote(c) for c in selected),
               quote(THROUGH_TABLE), quote(LEGACY_TASKRESULT_TABLE)))
        # one row per association of an opted-in task, so the whole set is read
        # at once rather than one query per process
        fetched = cursor.fetchall()

    evidence = []
    for row in fetched:
        padding = [None] * (len(EVIDENCED_COLUMNS) - len(selected))
        evidence.append((row[0], *list(row[1:]) + padding))
    return evidence


def outcome_log(task_id, status, date_done, date_created):
    """The log the state of one task justifies, or ``None`` for no statement.

    Only a state the backend wrote for *that* task is an outcome of its own. The
    state of the aggregate is never derived from it, which is why no ``status``
    or ``done_at`` of the process is touched anywhere in this node.
    """
    mapping = TERMINAL_TASK_STATES.get((status or '').strip().upper())
    if mapping is None:
        return None
    log_type, word = mapping
    return {
        'log_type': log_type,
        'description': '%s task %s of this process %s%s'
        % (CARRIED_MARKER, task_id, word,
           when_recorded(date_done, date_created)),
        'date': date_done or date_created or timezone.now(),
    }


def when_recorded(date_done, date_created):
    """The date the backend recorded, or the plain statement that there is none.

    A table which holds no date is said to hold none rather than being dated by
    this migration: the timestamp of the log row is then the only honest one
    there is.
    """
    recorded = date_done or date_created
    if recorded is None:
        return ', at a date the retired backend did not record'
    return ' on %s' % recorded.strftime('%Y-%m-%d %H:%M:%S %Z')


def carry_evidenced_task_results(apps, schema_editor):
    """Carry the ids and the verifiable outcomes D03 names (#1175, #1180).

    Written with ``update`` and ``bulk_create`` on the historical models, not
    with ``save``: the process must not run the lifecycle of the model it is
    stored in while that model is being migrated, and the post-save signal of
    ``notify/signals.py`` must not push a WebSocket update for rows which are
    history rather than progress.
    """
    connection = schema_editor.connection
    tasks = evidenced_tasks(connection)
    if tasks is None:
        logging.info(
            'notify.0006: no %s to read - the relation was already retired here '
            'by notify/0006 of #1179, which is the expected case for a '
            'deployment on the supported baseline', THROUGH_TABLE)
        return

    by_process = {}
    unreadable = 0
    for process_pk, task_id, status, date_done, date_created in tasks:
        # a task id which is no uuid has nowhere in the array, but the outcome
        # its row records is still a fact of that row and is still carried
        task_uuid = uuid.UUID(task_id) if UUID_TEXT.match(task_id or '') \
            else None
        if task_uuid is None:
            unreadable += 1
        by_process.setdefault(process_pk, []).append(
            (task_id, task_uuid, status, date_done, date_created))

    BackgroundProcess = apps.get_model('notify', 'BackgroundProcess')
    BackgroundProcessLog = apps.get_model('notify', 'BackgroundProcessLog')
    processes = BackgroundProcess.objects.using(connection.alias)
    # one read for all processes of the set, rather than one per association.
    # This is deliberately not ``AppendTaskIds`` of ``notify/models.py``: that
    # is ``array_cat``, which appends what it is given and would repeat an id the
    # process already owns, and its atomicity answers a concurrent registration
    # which a migration release has not started yet. As in the model, the ids
    # written are ``uuid.UUID`` and not their texts
    arrays = dict(processes.filter(pk__in=by_process)
                  .values_list('pk', 'celery_task_ids'))

    carried = 0
    logs = 0
    unknown = 0
    for process_pk, evidenced in by_process.items():
        if process_pk not in arrays:
            # the process is gone; its association and its outcomes go with it
            continue
        current = list(arrays[process_pk] or [])
        known = {str(task_id) for task_id in current}
        merged = list(current)
        rows = []
        for task_id, task_uuid, status, date_done, date_created in evidenced:
            if task_uuid is not None and str(task_uuid) not in known:
                merged.append(task_uuid)
                known.add(str(task_uuid))
            outcome = outcome_log(task_id, status, date_done, date_created)
            if outcome is None:
                unknown += 1
            else:
                rows.append(BackgroundProcessLog(
                    background_process_id=process_pk, **outcome))
        if merged != current:
            processes.filter(pk=process_pk).update(celery_task_ids=merged)
            carried += 1
        if rows:
            BackgroundProcessLog.objects.using(
                connection.alias).bulk_create(rows)
            logs += len(rows)

    logging.info(
        'notify.0006: carried the task ids of %d of %d processes named by %s, '
        'wrote %d outcome logs, left %d tasks whose state is no outcome of their '
        'own unknown (%d associations of %d read here name a task id which is no '
        'uuid text and cannot be stored in the array)',
        carried, len(by_process), THROUGH_TABLE, logs, unknown,
        unreadable, len(tasks))


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
            carry_evidenced_task_results, migrations.RunPython.noop),
        migrations.RunPython(
            drop_retired_through_table, migrations.RunPython.noop),
    ]
