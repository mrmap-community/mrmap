from django.db.models.enums import TextChoices


class ProcessNameEnum(TextChoices):
    HARVESTING = 'harvesting'
    MONITORING = 'monitoring'
    REGISTERING = 'registering'


class LogTypeEnum(TextChoices):
    ERROR = 'error'
    WARNING = 'warning'
    INFO = 'info'
