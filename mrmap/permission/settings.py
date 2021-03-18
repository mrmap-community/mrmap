from permission.enums import PermissionEnum
from django.utils.translation import gettext_lazy as _

DEFAULT_ROLES = [
    {
        "verbose_name": _("Group Administrator"),
        "description": _("Permission role. Holds permissions to administrate groups."),
        "permissions": [
            PermissionEnum.CAN_CREATE_GROUP,
            PermissionEnum.CAN_DELETE_GROUP,
            PermissionEnum.CAN_EDIT_GROUP,
            PermissionEnum.CAN_ADD_USER_TO_GROUP,
            PermissionEnum.CAN_REMOVE_USER_FROM_GROUP,
            PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS,
        ],
    },
    {
        "verbose_name": _("Organization Administrator"),
        "description": _("Permission role. Holds permissions to administrate organizations."),
        "permissions": [
            PermissionEnum.CAN_CREATE_ORGANIZATION,
            PermissionEnum.CAN_EDIT_ORGANIZATION,
            PermissionEnum.CAN_DELETE_ORGANIZATION,
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
