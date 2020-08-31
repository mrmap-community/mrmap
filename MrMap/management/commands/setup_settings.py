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

DEFAULT_GROUPS = [
    {
        "name": _("Group Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage groups."),
        "parent_group": None,
        "permissions": [
            Permission.can_create_group,
            Permission.can_delete_group,
            Permission.can_edit_group,
            Permission.can_add_user_to_group,
            Permission.can_remove_user_from_group,
            Permission.can_toggle_publish_requests,
            Permission.can_request_to_become_publisher,
        ]
    },
    {
        "name": _("Organization Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage organizations."),
        "parent_group": None,
        "permissions": [
            Permission.can_create_organization,
            Permission.can_edit_organization,
            Permission.can_delete_organization,
            Permission.can_remove_publisher,
        ]
    },
    {
        "name": _("Editor"),
        "description": _("Permission group. Holds users which are allowed to edit metadata or activate resources."),
        "parent_group": None,
        "permissions": [
            Permission.can_activate_resource,
            Permission.can_edit_metadata,
            Permission.can_edit_metadata,
        ]
    },
    {
        "name": _("Controller"),
        "description": _("Permission group. Holds users which are allowed to access and download logs or generate an API token."),
        "parent_group": None,
        "permissions": [
            Permission.can_generate_api_token,
            Permission.can_access_logs,
            Permission.can_download_logs,
        ]
    },
    {
        "name": _("Resource Administrator"),
        "description": _("Permission group. Holds users which are allowed to manage resource. This includes e.g. registration or removing of services and managing publisher requests."),
        "parent_group": "Editor",
        "permissions": [
            Permission.can_activate_resource,
            Permission.can_update_resource,
            Permission.can_register_resource,
            Permission.can_remove_resource,
            Permission.can_add_dataset_metadata,
            Permission.can_remove_dataset_metadata,
            Permission.can_toggle_publish_requests,
            Permission.can_remove_publisher,
            Permission.can_request_to_become_publisher,
        ]
    },
]