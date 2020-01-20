import django_filters
from .models import Layer

class ChildLayerFilter(django_filters.FilterSet):
    child_layer_title = django_filters.CharFilter(field_name='metadata', lookup_expr='title__icontains', label='Layer title contains')

    class Meta:
        model = Layer
        fields = []
