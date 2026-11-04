from django.db.models.enums import TextChoices


class ProbeOriginEnum(TextChoices):
    """How a monitoring probe came to exist.

    ``manual`` is the default and the state of every row which existed before
    the generated probes of the monitoring epic were introduced; ``generated``
    marks a probe which an explicit apply of a probe preview persisted.
    """

    MANUAL = "manual", "Manual"
    GENERATED = "generated", "Generated"
