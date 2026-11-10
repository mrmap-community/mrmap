.. _background-operations:

====================
Background operations
====================

A ``BackgroundProcess`` (``notify/models.py``) is what the deployment answers
when it is asked *what is it doing right now*. Harvests, service updates,
monitoring runs and registrations all report into one process, so the process is
the only place where a client of the background job center of the frontend
(#1203) can follow one logical operation from the moment it was made until it
decided about itself.

Issue #1207 normalized what that answer says. The rule behind all of it: **one
question, one answer.** A screen must not assemble a state out of columns, and
no reporter has to remember to maintain a second truth next to the fields it
already writes.

Where it lives
===============

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Code
     - Responsibility
   * - ``notify/models.py``
     - the stored columns of the reporting: the revision, the attention flag and
       the three retry fields. All of them are ``editable=False``: they are
       written by reporters, never by a client.
   * - ``notify/managers.py``
     - ``process_info()`` annotates the derived ``state`` and ``error_summary``
       over the stored fields; ``report``, ``raise_steps``, ``report_retry`` and
       ``set_action_required`` are the only writers, and ``_apply`` counts the
       revision in the same ``UPDATE``.
   * - ``notify/enums.py``
     - ``OperationStateEnum`` and its ``derive()``, the python mirror of the
       annotation for an instance which has none yet.
   * - ``notify/tasks.py``
     - the celery ``task_retry`` receiver which mirrors a retried task onto its
       process, and the task base which writes progress reports.
   * - ``notify/filters.py``, ``notify/views.py``, ``notify/serializers.py``
     - what the api answers and asks: ``state``, ``errorSummary``, ``revision``,
       the retry fields, ``filter[state]``, ``filter[relatedId]`` and the sorts by
       ``state`` and ``revision``.

The api of the process is unchanged in everything it answered before: the
contract is additive.

The state
=========

The stored ``status`` answers what the last reporter wrote. It cannot tell an
operation which waits for a worker apart from one whose work does not know its
steps, which one sits between two attempts and which one stands until a human
decides. The derived ``state`` answers all of it with one of eight names:

.. list-table::
   :header-rows: 1
   :widths: 22 30 48

   * - State
     - Reads
     - What a client renders
   * - ``queued``
     - status ``PENDING``
     - waiting for a worker
   * - ``running``
     - active, knows its total steps
     - a progress bar with a denominator
   * - ``running_indeterminate``
     - active, no or zero total steps
     - an indeterminate bar
   * - ``retrying``
     - active, an open retry window
     - waiting for the next attempt
   * - ``action_required``
     - active, a reporter asked a human for a decision
     - needs attention, does not move by itself
   * - ``failed`` / ``completed`` / ``aborted``
     - the terminal statuses
     - decided about itself

The state is **derived, never stored**. It is annotated by ``process_info()``
over ``status``, ``action_required``, ``retry_scheduled_until`` and
``total_steps``, so any report which moves one of them moves the state with it.
The order of the cases is the meaning and is fixed by the tests of
``tests/django/notify/test_operation_states.py``:

1. a process which decided about itself is never rendered as waiting, whatever
   its flag or its retry window still says;
2. ``PENDING`` is queued;
3. only an active process can need attention, wait for a retry, or not know its
   steps - attention before retry before indeterminate.

``OperationStateEnum.derive()`` is the same decision in python. It is used by
the serializer for an instance which was not read through ``process_info()`` -
the answer of the asynchronous api renders a process it created one moment ago,
and that instance carries no annotation. The tests hold the two answers against
each other over the whole table of stored combinations, so a change to one side
that forgets the other goes red.

Revision: the order of the reports
==================================

The messages of one operation reach a client over a channel layer which may
deliver them out of order, and the content of two messages does not tell which
one is the newer. Every report therefore carries the **revision** it reported:
a per-process counter, incremented by the database (``F("revision") + 1``)
inside the very ``UPDATE`` which moves the state, so concurrent reporters
cannot read each other's increment away. A client which receives an older
revision of a process it already knows drops it - that is what the consumer of
#1205 does with it.

Two writers, one rule:

- every queryset write of the reporters goes through ``BackgroundProcessManager
  ._apply``, which counts it;
- every ``save()`` of an existing process (an abort through the api is the one
  path left) counts it too and reloads the number, so the instance the response
  renders answers the revision and not the expression the database computed.

A new process starts at ``0``.

Progress
========

The contract answers the progress with its numerator and denominator as they are
stored - ``doneSteps``, ``totalSteps`` - and the percentage the overview
annotates, ``progress``. Where no denominator is known, ``totalSteps`` is
``null`` and the state is ``running_indeterminate``; a client must not render a
percentage out of a numerator alone. Completed processes are reported as done:
``report()`` sets the numerator to the denominator, because the completion of
the work is the proof that its steps are over.

Retries
=======

A retried task neither failed nor progressed: the operation waits for its next
attempt. The celery ``task_retry`` signal mirrors it onto the process
(``report_retry``), which adds one to ``retryCount``, stores what the task
failed on in ``retryReason`` and opens the window ``retryScheduledUntil``.
While that window is open the state reads ``retrying``.

- **The window comes from celery, not from a guess.** Whoever asked for the
  retry handed a delay with it: the ``when`` of the ``Retry`` exception - the
  seconds of an exponential backoff the autoretry decorator computed, or an
  explicit countdown or ``eta``. Only a retry which ran without any of them has
  to be estimated, and then with celery's own
  ``get_exponential_backoff_interval`` and the policy of the task, not with an
  invented formula.
- **The window closes by itself.** It is not a write which ends it; the state
  simply stops holding when the moment passed. The first progress report of the
  task clears it explicitly, because the operation demonstrably works again.
- **The counts are per operation.** They are never reset by a report which does
  not end the operation, and a process which decided about itself is not moved
  at all, like every other report.

Action required
===============

``action_required`` is the one flag of the contract that is stored, because its
verdict is not derivable: a human is awaited, and only the reporter knows that.
It is deliberately not answered by the api - the state answers it - and it has
exactly two owners:

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Owner
     - Decision
   * - the import watchdog of #1038 (``registry/tasks/harvest.py``)
     - sets it when the import backlog of a harvest stands untouched while the
       broker still holds its messages, and clears it when the backlog drains
       again. The watchdog is the only writer for a harvest: its beat fires over
       the same stall repeatedly and the flag flips once.
   * - ``ServiceUpdateJob.report_process``
     - an update whose mapping must be reviewed is an operation which stands.
       The flag follows the status of the job on every report, so answering the
       review clears it without any reporter having to remember.

A flag which does not change is not written at all: ``set_action_required``
filters ``only_if=Q(action_required=not flag)``, because a broadcast which says
nothing new is noise for every open overview. A terminal process is never
written - and a flag which was set before the operation decided stays behind the
terminal case of the state, where it can do no harm.

Grouping, filtering and sorting
===============================

One group of the job center is the set of operations which report about one
resource. The process already names its resource with ``related_resource_type``
plus ``related_id`` (its generic relation), so no new join was needed - and none
was introduced: this contract adds **no** ``GenericForeignKey``, no second
lookup table and no new model.

- ``filter[relatedId]`` and ``filter[relatedId.in]`` answer the operations of
  one resource, or of a chosen set of them.
- ``filter[state]`` and ``filter[state.in]`` ask for the states a tab renders;
  the values are the names above, never a number, and an unknown name is refused
  with ``400`` and ``invalid_choice`` like every other choice filter.
- ``sort=state`` and ``sort=revision`` order the answer by the annotation and by
  the counter. ``progress`` and ``dateCreated`` stay as they were.

Child work is not flattened into the operation and this contract adds no second
enumeration of it: what a process exposes for the work it reports stays exactly
as it was. Only the question of the operation itself is normalized here.

``errorSummary`` is what the operation last told as an error - the newest error
log of it, annotated over the list with a single subquery, so the drawer of the
job center renders it per row without one query per row. Where an instance was
not read through ``process_info()`` - a single object rendered straight after
its creation - the serializer answers the same question for that one process.

Tests
=====

The contract is held in three places, because it spans the derivation, the api
and the reporters:

- ``tests/django/notify/test_operation_states.py`` — the annotation against its
  python mirror over every combination of the stored fields, the revision over
  the sequence of reports, the error summary, the retry and attention writers,
  the ``task_retry`` receiver and the state filter.
- ``tests/django/notify/test_backgroundprocess_api.py`` — what the api answers
  and asks, including the serializer without an annotation.
- ``tests/django/registry/models/tests_background_process.py`` and
  ``tests/django/registry/tasks/tests_harvest_import_watchdog.py`` — the
  reporters: an update which waits for a review and a harvest whose import
  stalled answer the same state their own verdict decided.

The acceptance scenarios of the endpoint live in
``tests/behave/features/json:api/notify/backgroundprocess/``.
