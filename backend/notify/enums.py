from django.db.models.enums import TextChoices


class ProcessNameEnum(TextChoices):
    HARVESTING = 'harvesting'
    MONITORING = 'monitoring'
    REGISTERING = 'registering'
