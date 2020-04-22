"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.09.19

"""

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}

API_CACHE_TIME = 60*30  # 30 minutes
API_ALLOWED_HTTP_METHODS = [
    "get",
    "post",
    "head",
]

CATALOGUE_DEFAULT_ORDER = "hits"
METADATA_DEFAULT_ORDER = "hits"
SERVICE_DEFAULT_ORDER = "id"
LAYER_DEFAULT_ORDER = "id"
GROUP_DEFAULT_ORDER = "name"
ORGANIZATION_DEFAULT_ORDER = "organization_name"

SUGGESTIONS_MAX_RESULTS = 10