"""
Django settings for MrMap project.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

# Include other settings files (DO NOT TOUCH THESE!)
from MrMap.sub_settings.django_settings import *
from MrMap.sub_settings.dev_settings import *
from MrMap.sub_settings.db_settings import *
from MrMap.sub_settings.logging_settings import *
from api.settings import REST_FRAMEWORK


from structure.permissionEnums import PermissionEnum
from django.utils.translation import gettext_lazy as _

ALLOWED_HOSTS = [
    HOST_NAME,
    "127.0.0.1",
    "localhost",
]

# GIT repo links
GIT_REPO_URI = "https://github.com/mrmap-community/mrmap"
GIT_GRAPH_URI = "https://github.com/mrmap-community/mrmap/graph"

LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
LOGIN_URL = "login"

# Defines the semantic web information which will be injected on the resource html views
SEMANTIC_WEB_HTML_INFORMATION = {
    "legalName": "Zentrale Stelle GDI-RP",
    "email": "kontakt@geoportal.rlp.de",
    "addressCountry": "DE",
    "streetAddress": "Von-Kuhl-Straße 49",
    "addressRegion": "RLP",
    "postalCode": "56070",
    "addressLocality": "Koblenz",
}

# Defines the timespan for fetching the last activities on dashboard
LAST_ACTIVITY_DATE_RANGE = 7

# configure your proxy like "http://10.0.0.1:8080"
# or with username and password: "http://username:password@10.0.0.1:8080"
HTTP_PROXY = ""
PROXIES = {
    "http": HTTP_PROXY,
    "https": HTTP_PROXY,
}

# configure if you want to validate ssl certificates
# it is highly recommend keeping this to true
VERIFY_SSL_CERTIFICATES = True


# django-guardian
GUARDIAN_RAISE_403 = True

# django-guardian-roles
GUARDIAN_ROLES_OWNABLE_MODELS = ['service.Metadata',
                                 'monitoring.MonitoringRun',
                                 'monitoring.MonitoringResult',
                                 'monitoring.HealthState',
                                 'service.ProxyLog']

GUARDIAN_ROLES_OWNER_FIELD_ATTRIBUTE = 'owned_by_org'
GUARDIAN_ROLES_OLD_OWNER_FIELD_ATTRIBUTE = '_owned_by_org'

GUARDIAN_ROLES_ADMIN_ROLE_FOR_ROLE_ADMIN_ROLE = 'organization_administrator'
GUARDIAN_ROLES_OWNER_MODEL = 'structure.Organization'

DEFAULT_ROLES = [
    {
        "name": "organization_administrator",
        "verbose_name": _("Organization Administrator"),
        "description": _("Permission role. Holds permissions to administrate organizations."),
        "permissions": [
            PermissionEnum.CAN_VIEW_ORGANIZATION,
            PermissionEnum.CAN_EDIT_ORGANIZATION,
        ],
    },
    {
        "name": "resource_editor",
        "verbose_name": _("Resource Editor"),
        "description": _("Permission role. Holds permissions to edit metadata or activate resources."),
        "permissions": [
            PermissionEnum.CAN_VIEW_METADATA,
            PermissionEnum.CAN_ACTIVATE_RESOURCE,
            PermissionEnum.CAN_EDIT_METADATA,
        ],
    },
    {
        "name": "controller",
        "verbose_name": _("Controller"),
        "description": _("Permission role. Holds permissions to view proxylogs"
                         "an API token."),
        "permissions": [
            PermissionEnum.CAN_VIEW_PROXY_LOG,
        ],
    },
    {
        "name": "resource_administrator",
        "verbose_name": _("Resource Administrator"),
        "description": _("Permission role. Holds permissions to administrate resources."),
        "permissions": [
            PermissionEnum.CAN_VIEW_METADATA,
            PermissionEnum.CAN_ACTIVATE_RESOURCE,
            PermissionEnum.CAN_UPDATE_RESOURCE,
            PermissionEnum.CAN_REGISTER_RESOURCE,
            PermissionEnum.CAN_REMOVE_RESOURCE,
            PermissionEnum.CAN_ADD_DATASET_METADATA,
            PermissionEnum.CAN_REMOVE_DATASET_METADATA,
            PermissionEnum.CAN_VIEW_MONITORING_RUN,
            PermissionEnum.CAN_ADD_MONITORING_RUN,
            PermissionEnum.CAN_VIEW_MONITORING_RESULT,
            PermissionEnum.CAN_VIEW_HEALTH_STATE,
        ],
    },
]

