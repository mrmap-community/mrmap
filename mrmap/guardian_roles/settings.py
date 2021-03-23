from guardian_roles.enums import PermissionEnum
from django.utils.translation import gettext_lazy as _

from service.models import Metadata

DEFAULT_ROLES = [
    {
        "verbose_name": _("Organization Administrator"),
        "description": _("Permission role. Holds permissions to administrate organizations."),
        "permissions": [
            PermissionEnum.CAN_EDIT_ORGANIZATION,
            PermissionEnum.CAN_REMOVE_PUBLISHER,
        ],
    },
    {
        "verbose_name": _("Editor"),
        "description": _("Permission role. Holds permissions to edit metadata or activate resources."),
        "permissions": [
            PermissionEnum.CAN_ACTIVATE_RESOURCE,
            PermissionEnum.CAN_EDIT_METADATA,
        ],
    },
    {
        "verbose_name": _("Controller"),
        "description": _("Permission role. Holds permissions to view proxylogs"
                         "an API token."),
        "permissions": [
            PermissionEnum.CAN_VIEW_PROXY_LOG,
        ],
    },
    {
        "verbose_name": _("Resource Administrator"),
        "description": _("Permission role. Holds permissions to administrate resources."),
        "permissions": [
            PermissionEnum.CAN_ACTIVATE_RESOURCE,
            PermissionEnum.CAN_UPDATE_RESOURCE,
            PermissionEnum.CAN_REGISTER_RESOURCE,
            PermissionEnum.CAN_REMOVE_RESOURCE,
            PermissionEnum.CAN_ADD_DATASET_METADATA,
            PermissionEnum.CAN_REMOVE_DATASET_METADATA,
            PermissionEnum.CAN_REMOVE_PUBLISHER,
        ],
    },
]

OWNABLE_MODELS = [Metadata]

OWNER_FIELD_ATTRIBUTE = 'owned_by_org'
OLD_OWNER_FIELD_ATTRIBUTE = '_owned_by_org'
