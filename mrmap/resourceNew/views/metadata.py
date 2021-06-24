from django.http import HttpResponse
from django.views.generic import RedirectView
from django_filters.views import FilterView
from main.views import SecuredListMixin, SecuredUpdateView, SecuredDetailView, SecuredConfirmView
from resourceNew.filtersets.metadata import DatasetMetadataFilterSet, LayerMetadataFilterSet, ServiceMetadataFilterSet, \
    FeatureTypeMetadataFilterSet
from resourceNew.forms.metadata import ServiceMetadataModelForm, DatasetMetadataModelForm
from resourceNew.models import DatasetMetadata, ServiceMetadata, LayerMetadata, FeatureTypeMetadata
from resourceNew.tables.metadata import DatasetMetadataTable, ServiceMetadataTable, LayerMetadataTable, \
    FeatureTypeMetadataTable


class ServiceMetadataListView(SecuredListMixin, FilterView):
    model = ServiceMetadata
    table_class = ServiceMetadataTable
    filterset_class = ServiceMetadataFilterSet
    queryset = model.objects.for_table_view()


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


class ServiceMetadataXmlView(SecuredDetailView):
    model = ServiceMetadata
    content_type = "application/xml"
    queryset = ServiceMetadata.objects.all().select_related("service__proxy_setting", "document")

    def render_to_response(self, context, **response_kwargs):
        doc = self.service.document.xml
        if hasattr(self.object.service, "proxy_setting") and self.object.service.proxy_setting.camouflage:
            doc = self.object.document.camouflaged(request=self.request)
        return HttpResponse(content=doc,
                            content_type=self.content_type)


class DatasetMetadataUpdateView(SecuredUpdateView):
    model = DatasetMetadata
    form_class = DatasetMetadataModelForm


class DatasetMetadataRestoreView(SecuredConfirmView):
    model = DatasetMetadata

    def form_valid(self, form):
        self.object.restore()
        return super().form_valid(form=form)


class DatasetMetadataXmlView(SecuredDetailView):
    model = DatasetMetadata
    queryset = DatasetMetadata.objects.all().select_related("document").values("document__xml")
    content_type = "application/xml"

    def render_to_response(self, context, **response_kwargs):
        return HttpResponse(content=self.object.get("document__xml", None),
                            content_type=self.content_type)
