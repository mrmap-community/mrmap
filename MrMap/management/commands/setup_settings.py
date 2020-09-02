"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.07.20

"""

# PLEASE NOTE
# If you want to add more default groups, which inherit from one another:
# Make sure that the parent_group, has been declared above the child group in this list!
from structure.models import Permission
from django.utils.translation import gettext_lazy as _

from structure.permissionEnums import PermissionEnum

DEFAULT_GROUPS = [
    {
        "name": _("Group Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage groups."),
        "parent_group": None,
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
        "name": _("Organization Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage organizations."),
        "parent_group": None,
        "permissions": [
            PermissionEnum.CAN_CREATE_ORGANIZATION,
            PermissionEnum.CAN_EDIT_ORGANIZATION,
            PermissionEnum.CAN_DELETE_ORGANIZATION,
            PermissionEnum.CAN_REMOVE_PUBLISHER,
        ]
    },
    {
        "name": _("Editor"),
        "description": _("Permission group. Holds users which are allowed to edit metadata or activate resources."),
        "parent_group": None,
        "permissions": [
            PermissionEnum.CAN_ACTIVATE_RESOURCE,
            PermissionEnum.CAN_EDIT_METADATA,
            PermissionEnum.CAN_EDIT_METADATA,
        ]
    },
    {
        "name": _("Controller"),
        "description": _("Permission group. Holds users which are allowed to access and download logs or generate an API token."),
        "parent_group": None,
        "permissions": [
            PermissionEnum.CAN_GENERATE_API_TOKEN,
            PermissionEnum.CAN_ACCESS_LOGS,
            PermissionEnum.CAN_DOWNLOAD_LOGS,
        ]
    },
    {
        "name": _("Resource Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage resource. This includes e.g. registration or removing of services and managing publisher requests."),
        "parent_group": "Editor",
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
        ]
    },
]

DEFAULT_ROLE_NAME = "_default_"
