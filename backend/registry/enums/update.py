from django.utils.translation import gettext_lazy as _
from extras.enums import SmartIntegerChoices


class ServiceUpdateConflictEnum(SmartIntegerChoices):
    """ Defines all service update conflict types """
    METADATA_HAS_CHANGED = 1, _("Metadata has changed")
    CONTACT_HAS_CHANGED = 2, _("Contact has changed")


class LayerTreeConflictTypeEnum(SmartIntegerChoices):
    """ Defines all conflict types """
    POSSIBLE_LAYER_RENAME = 1, _("Possible layer rename")
    LAYER_PARENT_CHANGED = 2, _("Layer parent changed")
    LAYER_GROUP_STRUCTURE_CHANGED = 3, _("Layer group structure changed")
    AMBIGUOUS_LAYER_MAPPING = 4, _("Ambiguous layer mapping")
    LAYER_REMOVED = 5, _("Layer removed")
    LAYER_STRUCTURE_CHANGED = 6, _("Layer structure changed")


class LayerTreeConflictResolutionEnum(SmartIntegerChoices):
    """ Defines all resolutions """


class UpdateJobStatusEnum(SmartIntegerChoices):
    OK = 0, _("OK")
    UPDATING = 1, _("Updating")
    REVIEW_REQUIRED = 2, _("Review required")
    ERROR = 3, _("Error")
    WAITING_FOR_PROCESSING = 4, _("Waiting for processing")
