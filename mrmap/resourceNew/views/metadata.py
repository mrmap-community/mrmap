from django_filters.views import FilterView
from main.views import SecuredListMixin
from resourceNew.filtersets.metadata import DatasetMetadataFilterSet, LayerMetadataFilterSet
from resourceNew.models import DatasetMetadata, ServiceMetadata, LayerMetadata, FeatureTypeMetadata
from resourceNew.tables.metadata import DatasetMetadataTable, ServiceMetadataTable, LayerMetadataTable, \
    FeatureTypeMetadataTable


class ServiceMetadataListView(SecuredListMixin, FilterView):
    model = ServiceMetadata
    table_class = ServiceMetadataTable
    queryset = model.objects.for_table_view()


class LayerMetadataListView(SecuredListMixin, FilterView):
    model = LayerMetadata
    table_class = LayerMetadataTable
    filterset_class = LayerMetadataFilterSet
    queryset = model.objects.for_table_view()


class FeatureTypeMetadataListView(SecuredListMixin, FilterView):
    model = FeatureTypeMetadata
    table_class = FeatureTypeMetadataTable
    queryset = model.objects.for_table_view()


class DatasetMetadataListView(SecuredListMixin, FilterView):
    model = DatasetMetadata
    table_class = DatasetMetadataTable
    filterset_class = DatasetMetadataFilterSet
    queryset = model.objects.for_table_view()
