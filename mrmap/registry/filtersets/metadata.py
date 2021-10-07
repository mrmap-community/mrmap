import django_filters
from registry.models import DatasetMetadata


class DatasetMetadataFilterSet(django_filters.FilterSet):

    class Meta:
        model = DatasetMetadata
        fields = {
            "title": ["icontains", ],
            "id": ["in", ],
            "self_pointing_layers__id": ["in", ],
            "self_pointing_feature_types__id": ["in", ]
        }
