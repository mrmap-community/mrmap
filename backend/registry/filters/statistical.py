from django_filters import FilterSet, UUIDFilter
from registry.models.service import FeatureType


class StatisticalFeatureTypePerServiceFilterSet(FilterSet):
    service = UUIDFilter()

    class Meta:
        model = FeatureType.change_log.model
        fields = ('service',)
