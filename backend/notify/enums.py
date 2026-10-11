from django.db.models.enums import TextChoices
from extras.enums import SmartIntegerChoices


class ProcessNameEnum(TextChoices):
    HARVESTING = 'harvesting'
    MONITORING = 'monitoring'
    REGISTERING = 'registering'


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
