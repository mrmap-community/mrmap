from django.db.models.enums import TextChoices
from django.utils import timezone
from extras.enums import SmartIntegerChoices


class ProcessNameEnum(TextChoices):
    HARVESTING = 'harvesting'
    MONITORING = 'monitoring'
    REGISTERING = 'registering'
    UPDATE = 'update'


class LogTypeEnum(TextChoices):
    ERROR = 'error'
    WARNING = 'warning'
    INFO = 'info'


class ProcessStatusEnum(SmartIntegerChoices):
    PENDING = 0, 'pending'
    RUNNING = 1, 'running'
    COMPLETED = 2, 'completed'
    FAILED = 3, 'failed'
    ABORTED = 4, 'aborted'


class JobStateEnum(TextChoices):
    """The logical states of a background job as the Background Job Center
    renders them (#1207).

    This is the display contract of the drawer, derived from the stored
    :class:`ProcessStatusEnum` and the retry state of the process' threads:

    * ``queued``: the work is scheduled but no worker holds it yet;
    * ``running``: a worker holds the work; with no known total the drawer
      shows an indeterminate progress, with a total the determinate one;
    * ``retrying``: a worker of the process is held in a celery retry - the
      work will be attempted again, it is not lost;
    * ``failed`` / ``aborted``: the job decided against its work and needs
      action - the error summary tells what to look at;
    * ``completed``: the job is done.
    """

    QUEUED = 'queued'
    RUNNING = 'running'
    RETRYING = 'retrying'
    FAILED = 'failed'
    COMPLETED = 'completed'
    ABORTED = 'aborted'


class OperationStateEnum(TextChoices):
    """Normalized state of a background operation (#1207).

    The stored ``ProcessStatusEnum`` answers what the last reporter wrote
    about the operation; it cannot tell an operation which waits for a worker
    apart from one whose work does not know its steps, which one is between
    two attempts or which one stands until a human decides. Those are the
    questions the background job center of the frontend renders as tabs and
    progress bars, so the api answers them with this one state, derived from
    the stored status together with the retry, attention and step fields of
    the process.

    The state is derived, never stored: it is annotated over the stored
    fields by ``BackgroundProcessManager.process_info`` and answered by the
    serializer, so a report which moves any of them moves the state with it
    and no reporter has to remember to maintain a second truth.
    """

    QUEUED = "queued", "queued"
    RUNNING = "running", "running"
    RUNNING_INDETERMINATE = "running_indeterminate", "running indeterminate"
    RETRYING = "retrying", "retrying"
    ACTION_REQUIRED = "action_required", "action required"
    FAILED = "failed", "failed"
    COMPLETED = "completed", "completed"
    ABORTED = "aborted", "aborted"

    @classmethod
    def derive(cls, status, action_required=False,
               retry_scheduled_until=None, total_steps=None, at=None):
        """Derive the state of an operation from its stored fields.

        This is the python mirror of the annotation which
        ``BackgroundProcessManager.process_info`` builds; both have to answer
        the same state for the same stored values, which the tests of the
        operation states hold against the same table of cases. The serializer
        uses it for an instance which was not read through ``process_info``
        - a process which was just created has no annotation to carry.

        Args:
            status (ProcessStatusEnum): the stored status of the process
            action_required (bool): whether a reporter told the process that
                a human decision is needed before the work goes on
            retry_scheduled_until: the moment until which a retry of a task
                of the operation is expected, or None when none is open
            total_steps: the denominator the operation reports, None or a
                non-positive number when the operation does not know it
            at: the moment the window of an open retry is measured against,
                now by default
        """
        if at is None:
            at = timezone.now()
        status = ProcessStatusEnum(status)
        if status == ProcessStatusEnum.COMPLETED:
            return cls.COMPLETED.value
        if status == ProcessStatusEnum.FAILED:
            return cls.FAILED.value
        if status == ProcessStatusEnum.ABORTED:
            return cls.ABORTED.value
        if status == ProcessStatusEnum.PENDING:
            return cls.QUEUED.value
        if action_required:
            return cls.ACTION_REQUIRED.value
        if retry_scheduled_until is not None and retry_scheduled_until > at:
            return cls.RETRYING.value
        if not total_steps:
            return cls.RUNNING_INDETERMINATE.value
        return cls.RUNNING.value
