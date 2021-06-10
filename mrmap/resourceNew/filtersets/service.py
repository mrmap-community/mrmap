import django_filters
from resourceNew.models.service import Layer, FeatureType, FeatureTypeElement


class LayerFilterSet(django_filters.FilterSet):
    title = django_filters.CharFilter(field_name='metadata__title', lookup_expr='icontains')

    class Meta:
        model = Layer
        fields = {
            "id": ["in", ],
            "parent": ["exact", ],
            "service__id": ["in", ]
        }


class FeatureTypeFilterSet(django_filters.FilterSet):
    title = django_filters.CharFilter(field_name='metadata__title', lookup_expr='icontains')

    class Meta:
        model = FeatureType
        fields = {
            "id": ["in", ],
            "service__id": ["in", ]
        }


class FeatureTypeElementFilterSet(django_filters.FilterSet):
    class Meta:
        model = FeatureTypeElement
        fields = {
            "id": ["in", ],
            "name": ["icontains", ],
            "data_type": ["icontains"],
            "feature_type__id": ["in", ]
        }

