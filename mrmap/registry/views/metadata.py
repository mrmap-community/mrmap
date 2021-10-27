from django_filters.views import FilterView
from extras.views import SecuredListMixin, SecuredUpdateView, SecuredConfirmView
from registry.filtersets.metadata import DatasetMetadataFilterSet
from registry.forms.metadata import ServiceMetadataModelForm, DatasetMetadataModelForm
from registry.models import DatasetMetadata, ServiceMetadata
from registry.tables.metadata import DatasetMetadataTable


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
