from django.utils.translation import gettext_lazy as _
from extras.enums import SmartIntegerChoices


class UpdateJobStatusEnum(SmartIntegerChoices):
    OK = 0, _("OK")
    UPDATING = 1, _("Updating")
    REVIEW_REQUIRED = 2, _("Review required")
    ERROR = 3, _("Error")
    WAITING_FOR_PROCESSING = 4, _("Waiting for processing")
