from permission.enums import PermissionEnum, RoleNameEnum
from django.utils.translation import gettext_lazy as _


DEFAULT_ROLES = [
    {
        "name": RoleNameEnum.GROUP_ADMIN.value,
        "verbose_name": _("Group Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage groups."),
        "permissions": [
            PermissionEnum.CAN_CREATE_GROUP,
            PermissionEnum.CAN_DELETE_GROUP,
            PermissionEnum.CAN_EDIT_GROUP,
            PermissionEnum.CAN_ADD_USER_TO_GROUP,
            PermissionEnum.CAN_REMOVE_USER_FROM_GROUP,
            PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS,
            PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER,
        ]
    },
    {
        "name": RoleNameEnum.ORGANIZATION_ADMIN.value,
        "verbose_name": _("Organization Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage organizations."),
        "permissions": [
            PermissionEnum.CAN_CREATE_ORGANIZATION,
            PermissionEnum.CAN_EDIT_ORGANIZATION,
            PermissionEnum.CAN_DELETE_ORGANIZATION,
            PermissionEnum.CAN_REMOVE_PUBLISHER,
        ]
    },
    {
        "name": RoleNameEnum.EDITOR_ADMIN.value,
        "verbose_name": _("Editor"),
        "description": _("Permission group. Holds users which are allowed to edit metadata or activate resources."),
        "permissions": [
            PermissionEnum.CAN_ACTIVATE_RESOURCE,
            PermissionEnum.CAN_EDIT_METADATA,
            PermissionEnum.CAN_EDIT_METADATA,
        ]
    },
    {
        "name": RoleNameEnum.CONTROLLER_ADMIN.value,
        "verbose_name": _("Controller"),
        "description": _("Permission group. Holds users which are allowed to access and download logs or generate "
                         "an API token."),
        "permissions": [
            PermissionEnum.CAN_GENERATE_API_TOKEN,
            PermissionEnum.CAN_ACCESS_LOGS,
            PermissionEnum.CAN_DOWNLOAD_LOGS,
        ]
    },
    {
        "name": RoleNameEnum.RESOURCE_ADMIN.value,
        "verbose_name": _("Resource Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage resource. This includes e.g. "
                         "registration or removing of services and managing publisher requests."),
        "permissions": [
            PermissionEnum.CAN_ACTIVATE_RESOURCE,
            PermissionEnum.CAN_UPDATE_RESOURCE,
            PermissionEnum.CAN_REGISTER_RESOURCE,
            PermissionEnum.CAN_REMOVE_RESOURCE,
            PermissionEnum.CAN_ADD_DATASET_METADATA,
            PermissionEnum.CAN_REMOVE_DATASET_METADATA,
            PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS,
            PermissionEnum.CAN_REMOVE_PUBLISHER,
            PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER,
            PermissionEnum.CAN_RUN_MONITORING,
            PermissionEnum.CAN_RUN_VALIDATION,
        ]
    },
]
