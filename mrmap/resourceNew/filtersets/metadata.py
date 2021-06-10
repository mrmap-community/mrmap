import django_filters
from resourceNew.models import DatasetMetadata, LayerMetadata


class LayerMetadataFilterSet(django_filters.FilterSet):

    class Meta:
        model = LayerMetadata
        fields = {
            "title": ["icontains", ],
            "id": ["in", ],
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
