"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.09.19

"""
from service.helper.enums import MetadataRelationEnum

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

API_CACHE_KEY_PREFIX = "REST_API_CACHE"
API_CACHE_TIME = 60 * 60  # 60 minutes
API_ALLOWED_HTTP_METHODS = [
    "get",
    "post",
    "head",
]

# Settings on how the ?q parameter of the API will perform
# You should always keep the keyword setting on True, since this is the way a spatial data infrastructure is supposed to work!
# Enable the other settings for further combinations. Test a little bit around and see what configuration fits the best for
# your environment.
# PLEASE NOTE: Enabling title and abstract querying next to keywords leads to duplicate entries in the resulting set.
# Adding a distinct search would increase the response time too much, therefore the current way to go is to accept the fact
# that some results might be duplicated.
API_QUERY_ON_KEYWORDS = True  # The way OGC services should be queried in a perfect world. If the metadata are bad, you won't find anything.
API_QUERY_ON_TITLE = False  # Extend the keyword querying by enabling this option. Be aware this slows down the DB lookup.
API_QUERY_ON_ABSTRACT = False  # Extend the keyword querying by enabling this option. Be aware this slows down the DB lookup.

CATALOGUE_DEFAULT_ORDER = "hits"
METADATA_DEFAULT_ORDER = "hits"
SERVICE_DEFAULT_ORDER = "id"
LAYER_DEFAULT_ORDER = "id"
GROUP_DEFAULT_ORDER = "name"
ORGANIZATION_DEFAULT_ORDER = "organization_name"

SUGGESTIONS_MAX_RESULTS = 10

# Defines a filter to exclude some MetadataRelations, which shall not appear in the API
API_EXCLUDE_METADATA_RELATIONS = {
    "relation_type__in": [
        MetadataRelationEnum.HARVESTED_THROUGH.value,
        MetadataRelationEnum.HARVESTED_PARENT.value,
    ]
}
