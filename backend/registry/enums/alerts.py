from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _


class ServiceAlertSeverity(TextChoices):
    """How much attention a service needs.

    The severity is what a client colours a signal with and sorts a list by, so
    the values are chosen to keep their order when they are sorted as text:
    an error before a warning.
    """
    ERROR = "error", _("error")
    WARNING = "warning", _("warning")


class ServiceAlertCategory(TextChoices):
    """The state of a service which an administrator has to attend to.

    Every category is derived from a state which exists in the registry - see
    registry/querys/alerts.py - and names the decision or the fix a service
    awaits. The categories of a problem which needs a decision are answered with
    the severity WARNING, the categories of a problem which already happened
    with the severity ERROR.
    """
    MONITORING_FAILED = "monitoring_failed", _("monitoring failed")
    MONITORING_OVERDUE = "monitoring_overdue", _("monitoring overdue")
    UPDATE_REVIEW_REQUIRED = "update_review_required", _("update review required")
    UPDATE_FAILED = "update_failed", _("update failed")
    UPDATE_OVERDUE = "update_overdue", _("update overdue")
    HARVESTING_INCOMPLETE = "harvesting_incomplete", _("harvesting incomplete")
