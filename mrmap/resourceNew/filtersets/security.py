import django_filters
from dal import autocomplete
from django.contrib.gis.geos import GEOSGeometry

from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxyLog, ExternalAuthentication
from django.utils.translation import gettext_lazy as _


class ExternalAuthenticationFilterSet(django_filters.FilterSet):
    class Meta:
        model = ExternalAuthentication
        fields = {
            "id": ["in"],
            "secured_service__id": ["in", ],
        }


class ServiceAccessGroupFilterSet(django_filters.FilterSet):
    class Meta:
        model = ServiceAccessGroup
        fields = {
            "id": ["in"],
            "name": ["icontains"],
            "description": ["icontains", ],
        }


class AllowedOperationFilterSet(django_filters.FilterSet):
    class Meta:
        model = AllowedOperation
        fields = {
            "id": ["in"],
            "description": ["icontains", ],
            "allowed_groups__id": ["in"],
            "secured_service__id": ["in"],
            "secured_layers__id": ["in"],
            "secured_feature_types__id": ["in"],
            "operations__operation": ["icontains"],
        }


class ProxyLogFilterSet(django_filters.FilterSet):
    class Meta:
        model = ProxyLog
        fields = {
            "id": ["in"],
            "service__id": ["in"],
            "user__id": ["in"],
            "operation__operation": ["in"],
            "uri": ["icontains"],
            "response_wfs_num_features": ["icontains"],
            "response_wms_megapixel": ["icontains"],
        }
