from django.db.models.enums import IntegerChoices
from django.utils.translation import gettext_lazy as _


class CollectingStatenEnum(IntegerChoices):
    """ Defines sources for categories
    """
    NEW = 1, _("new")
    UPDATED = 2, _("updated")
    EXISTING = 3, _("existing")
    DUPLICATED = 0, _("duplicated")


class HarvestingPhaseEnum(IntegerChoices):
    PENDING = 0, _("pending")
    GET_TOTAL_RECORDS_COUNT = 1, _("get total records count")
    DOWNLOAD_RECORDS = 2, ("download records")
    RECORDS_TO_DB = 3, _("records to db")
    COMPLETED = 4, _("completed")
    ABORTED = 5, _("aborted")
    ABORT = 4711, _("abort")


class LogLevelEnum(IntegerChoices):
    FATAL = 0, _("Fatal")
    ERROR = 1, _("Error")
    WARNING = 2, _("Warning")
    INFO = 3, _("Info")
    DEBUG = 4, _("Debug")


class LogKindEnum(IntegerChoices):
    REMOTE_ERROR = 0, _("Remote Error")
    COUNT_MISSMATCH = 1, _("received records count missmatch")
    __empty__ = _("(Unknown)")
