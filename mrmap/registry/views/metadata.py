from django_filters.views import FilterView
from extras.views import SecuredListMixin, SecuredUpdateView, SecuredConfirmView
from registry.filtersets.metadata import DatasetMetadataFilterSet, LayerMetadataFilterSet, \
    FeatureTypeMetadataFilterSet
from registry.forms.metadata import ServiceMetadataModelForm, DatasetMetadataModelForm
from registry.models import DatasetMetadata, ServiceMetadata, LayerMetadata, FeatureTypeMetadata
from registry.tables.metadata import DatasetMetadataTable, LayerMetadataTable, \
    FeatureTypeMetadataTable


class LayerMetadataListView(SecuredListMixin, FilterView):
    model = LayerMetadata
    table_class = LayerMetadataTable
    filterset_class = LayerMetadataFilterSet
    queryset = model.objects.for_table_view()


class FeatureTypeMetadataListView(SecuredListMixin, FilterView):
    model = FeatureTypeMetadata
    table_class = FeatureTypeMetadataTable
    filterset_class = FeatureTypeMetadataFilterSet
    queryset = model.objects.for_table_view()


class DatasetMetadataListView(SecuredListMixin, FilterView):
    model = DatasetMetadata
    table_class = DatasetMetadataTable
    filterset_class = DatasetMetadataFilterSet
    queryset = model.objects.for_table_view()


class ServiceMetadataUpdateView(SecuredUpdateView):
    model = ServiceMetadata
    form_class = ServiceMetadataModelForm


class DatasetMetadataUpdateView(SecuredUpdateView):
    model = DatasetMetadata
    form_class = DatasetMetadataModelForm


class DatasetMetadataRestoreView(SecuredConfirmView):
    model = DatasetMetadata

    def form_valid(self, form):
        self.object.restore()
        return super().form_valid(form=form)
