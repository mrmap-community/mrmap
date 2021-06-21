import django_filters
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxyLog


class ServiceAccessGroupFilterSet(django_filters.FilterSet):
    class Meta:
        model = ServiceAccessGroup
        fields = {
            "name": ["icontains"],
            "description": ["icontains", ],
        }


class AllowedOperationFilterSet(django_filters.FilterSet):
    class Meta:
        model = AllowedOperation
        fields = {
            "description": ["icontains", ],
            "allowed_groups__id": ["in"],
            "secured_service__id": ["in"],
            "operations__operation": ["icontains"],
        }


class ProxyLogFilterSet(django_filters.FilterSet):
    class Meta:
        model = ProxyLog
        fields = {
            "service__id": ["in"],
            "user__id": ["in"],
            "operation__operation": ["in"],
            "uri": ["icontains"],
            "response_wfs_num_features": ["icontains"],
            "response_wms_megapixel": ["icontains"],
        }
