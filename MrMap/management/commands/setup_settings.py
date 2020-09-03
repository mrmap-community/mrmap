"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.07.20

"""

# PLEASE NOTE
# If you want to add more default groups, which inherit from one another:
# Make sure that the parent_group, has been declared above the child group in this list!
from service.helper.enums import CategoryOriginEnum
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


CATEGORIES = {
    CategoryOriginEnum.INSPIRE.value: "https://www.eionet.europa.eu/gemet/getTopmostConcepts?thesaurus_uri=http://inspire.ec.europa.eu/theme/&language={}",
    CategoryOriginEnum.ISO.value: "http://inspire.ec.europa.eu/metadata-codelist/TopicCategory/TopicCategory.{}.json",
}

CATEGORIES_LANG = {
    "locale_1": "de",
    "locale_2": "fr",
}

LICENCES = [
    {
        "name": "Creative Commons 3.0",
        "identifier": "cc-by-nc-nd-3.0",
        "symbol_url": "http://i.creativecommons.org/l/by-nc-nd/3.0/de/88x31.png",
        "description": "Creative Commons: Namensnennung - Keine kommerzielle Nutzung - Keine Bearbeitungen 3.0 Deutschland",
        "description_url": "http://creativecommons.org/licenses/by-nc-nd/3.0/de/",
        "is_open_data": False,
    },
    {
        "name": "Creative Commons 3.0",
        "identifier": "cc-nc-3.0",
        "symbol_url": "http://i.creativecommons.org/l/by-nc/3.0/de/88x31.png",
        "description": "Creative Commons: Namensnennung - Keine kommerzielle Nutzung 3.0 Deutschland",
        "description_url": "http://creativecommons.org/licenses/by-nc/3.0/de/",
        "is_open_data": False,
    },
    {
        "name": "Creative Commons 3.0",
        "identifier": "cc-by-3.0",
        "symbol_url": "http://i.creativecommons.org/l/by/3.0/de/88x31.png",
        "description": "Creative Commons: Namensnennung 3.0 Deutschland",
        "description_url": "http://creativecommons.org/licenses/by/3.0/de/",
        "is_open_data": True,
    },
    {
        "name": "Datenlizenz Deutschland 1.0",
        "identifier": "dl-de-by-nc-1.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland – Namensnennung – nicht-kommerziell – Version 1.0",
        "description_url": "https://www.govdata.de/dl-de/by-nc-1-0",
        "is_open_data": False,
    },
    {
        "name": "Datenlizenz Deutschland 1.0",
        "identifier": "dl-de-by-1.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland – Namensnennung – Version 1.0",
        "description_url": "https://www.govdata.de/dl-de/by-1-0",
        "is_open_data": True,
    },
    {
        "name": "Datenlizenz Deutschland 2.0",
        "identifier": "dl-de-zero-2.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland – Zero – Version 2.0",
        "description_url": "https://www.govdata.de/dl-de/zero-2-0",
        "is_open_data": True,
    },
    {
        "name": "Datenlizenz Deutschland 2.0",
        "identifier": "dl-de-by-2.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland Namensnennung 2.0",
        "description_url": "https://www.govdata.de/dl-de/by-2-0",
        "is_open_data": True,
    },
    {
        "name": "Open Data Commons Open Database License",
        "identifier": "odc-odbl-1.0",
        "symbol_url": None,
        "description": "Open Data Commons Open Database License (ODbL)",
        "description_url": "http://opendatacommons.org/licenses/odbl/1.0/",
        "is_open_data": True,
    },
]