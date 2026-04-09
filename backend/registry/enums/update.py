from django.utils.translation import gettext_lazy as _
from extras.enums import SmartIntegerChoices


class UpdateJobStatusEnum(SmartIntegerChoices):
    NO_UPDATE_NEEDED = 0, _("No update needed")
    UPDATING = 1, _("Updating")
    REVIEW_REQUIRED = 2, _("Review required")
    ERROR = 3, _("Error")
    WAITING_FOR_PROCESSING = 4, _("Waiting for processing")
    UPDATED = 5, _("Updated")
    RESUME = 6, _("Resume")
