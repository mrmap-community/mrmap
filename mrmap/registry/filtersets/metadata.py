import django_filters
from registry.models import DatasetMetadata, FeatureTypeMetadata


class FeatureTypeMetadataFilterSet(django_filters.FilterSet):

    class Meta:
        model = FeatureTypeMetadata
        fields = {
            "title": ["icontains", ],
            "id": ["in", ],
            "described_object__id": ["in", ],
        }


class DatasetMetadataFilterSet(django_filters.FilterSet):

    class Meta:
        model = DatasetMetadata
        fields = {
            "title": ["icontains", ],
            "id": ["in", ],
            "self_pointing_layers__id": ["in", ],
            "self_pointing_feature_types__id": ["in", ]
        }
