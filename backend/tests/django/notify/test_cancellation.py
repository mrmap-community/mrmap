"""The abort of a process targets its work through the maintained ownership.

#1179 retired the `threads` relation to the legacy `TaskResult` table. What
a process aborts is what its registered task ids and the worker inspection
name: a message which no worker has picked up yet, work which is active or
reserved on a worker, and a retry which waits for its next attempt - and only
the work of the requested process.

The broker boundary is the `inspect` and `revoke` of the app in
`notify.models`. An inspection which answers nothing is the honest case of a
message no worker has read yet - the normal state right after a publication -
and not a shortcut around worker inspection.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess

INSPECT = "notify.models.app.control.inspect"
REVOKE = "notify.models.app.control.revoke"


def reported(task_id, process_pk, **extra_kwargs):
    """The entry an inspected worker answers for a task of a process.

    A worker reports the kwargs it received from the broker, and the broker
    transports them as strings, just as `get_related_task_ids` compares them.
    """
    kwargs = {"background_process_pk": str(process_pk)}
    kwargs.update(extra_kwargs)
    return {"kwargs": kwargs, "request": {"id": str(task_id)}}


def no_worker_answers(inspect):
    """The three answers of an inspection which reaches no worker at all."""
    for answer in ("active", "reserved", "scheduled"):
        getattr(inspect.return_value, answer).return_value = None


class CancellationOwnershipTests(TestCase):
    """Which ids an abort targets, and what is stored before it revokes."""

    def setUp(self):
        self.process = BackgroundProcess.objects.create(
            process_type="registering", phase="queued",
            description="a registration which may be aborted")

    def abort(self):
        self.process.phase = "abort"
        self.process.save(update_fields=["phase"])

    def test_a_queued_task_no_worker_has_picked_up_is_still_revoked(self):
        """The durable ownership, not the inspection, carries the queued case.

        The root task id is registered before its publication (see
        `test_registration_polling.py`); with the message still sitting on
        the broker, no worker can report about it and the stored id is the
        only handle the abort has.
        """
        task_id = uuid4()
        self.process.append_celery_task_ids([task_id])

        with patch(INSPECT) as inspect, patch(REVOKE) as revoke:
            no_worker_answers(inspect)
            self.assertEqual(
                self.process.get_related_task_ids(), [str(task_id)])
            self.abort()

        revoke.assert_called_once()
        self.assertEqual(
            set(revoke.call_args.args[0]), {str(task_id)})
        self.assertTrue(revoke.call_args.kwargs["terminate"])
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.ABORTED)
        self.assertIsNotNone(self.process.done_at)

    def test_the_work_a_worker_reports_is_revoked(self):
        """Active, reserved and scheduled work of the process are targeted.

        A retry whose next attempt a worker already holds is the scheduled
        answer; an active entry is the work which is running right now.
        """
        active = str(uuid4())
        reserved = str(uuid4())
        scheduled = str(uuid4())

        with patch(INSPECT) as inspect, patch(REVOKE) as revoke:
            inspect.return_value.active.return_value = {
                "worker-1": [reported(active, self.process.pk)]}
            inspect.return_value.reserved.return_value = {
                "worker-1": [reported(reserved, self.process.pk)]}
            inspect.return_value.scheduled.return_value = {
                "worker-1": [reported(scheduled, self.process.pk)]}
            self.abort()

        self.assertEqual(
            set(revoke.call_args.args[0]), {active, reserved, scheduled})

    def test_only_the_work_of_the_requested_process_is_targeted(self):
        """Neither another process' work nor a task of nobody is revoked."""
        mine = str(uuid4())
        other_process = BackgroundProcess.objects.create(
            process_type="registering", phase="queued",
            description="a second registration")
        others = str(uuid4())
        unclaimed = str(uuid4())
        self.process.append_celery_task_ids([mine])
        other_process.append_celery_task_ids([others])

        with patch(INSPECT) as inspect, patch(REVOKE) as revoke:
            active_tasks = [
                reported(mine, self.process.pk),
                reported(others, other_process.pk),
                # a task which was published without any process at all
                {"kwargs": {}, "request": {"id": unclaimed}},
            ]
            inspect.return_value.active.return_value = {
                "worker-1": active_tasks}
            inspect.return_value.reserved.return_value = None
            inspect.return_value.scheduled.return_value = None
            self.abort()

        self.assertEqual(set(revoke.call_args.args[0]), {mine})

    def test_a_retry_is_covered_by_the_id_it_kept(self):
        """A retried task is republished under its own id, which is stored.

        Between the attempts the message of the retry is on the broker: this
        inspection answers nothing for the registered root, and the stored id
        is what the abort still revokes - whichever attempt it meets.
        """
        root = str(uuid4())
        self.process.append_celery_task_ids([root])

        with patch(INSPECT) as inspect, patch(REVOKE) as revoke:
            no_worker_answers(inspect)
            self.abort()

        self.assertEqual(set(revoke.call_args.args[0]), {root})

    def test_completed_work_leaves_nothing_to_revoke_but_the_stored_id(self):
        """A task which ran to its end is not reported by any inspection.

        The id of a finished task is not a second live thing: revoking it is
        a no-op in celery. What the abort must still do - and does - is end
        the process and let no result-table decide what is unfinished.
        """
        finished = str(uuid4())
        self.process.append_celery_task_ids([finished])

        with patch(INSPECT) as inspect, patch(REVOKE) as revoke:
            no_worker_answers(inspect)
            self.abort()

        self.assertEqual(set(revoke.call_args.args[0]), {finished})
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.ABORTED)

    def test_a_process_without_any_work_revokes_nothing(self):
        """An empty ownership answers an empty revocation - no broker call."""
        with patch(INSPECT) as inspect, patch(REVOKE) as revoke:
            no_worker_answers(inspect)
            self.abort()

        revoke.assert_not_called()

    def test_the_abort_is_stored_before_the_blocking_inspection(self):
        """The row reads aborted while the very inspection call happens.

        Finding the tasks costs one blocking broadcast round trip per
        inspector call. The terminal outcome is stored before that call, so
        a slow or unreachable broker cannot keep the process looking alive
        for anything which reads the row meanwhile.
        """
        stored = {}

        def inspect_and_read_row():
            stored.update(
                BackgroundProcess.objects.filter(
                    pk=self.process.pk).values("status", "done_at").get())
            # and the call itself answers nothing, as a broker would which
            # the workers cannot reach
            inspector = MagicMock()
            for answer in ("active", "reserved", "scheduled"):
                getattr(inspector, answer).return_value = None
            return inspector

        self.process.append_celery_task_ids([uuid4()])
        with patch(REVOKE), patch(INSPECT, side_effect=inspect_and_read_row):
            self.abort()

        self.assertEqual(stored["status"], ProcessStatusEnum.ABORTED)
        self.assertIsNotNone(stored["done_at"])
