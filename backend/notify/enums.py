from django.db.models.enums import TextChoices
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
