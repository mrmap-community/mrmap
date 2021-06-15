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


class ServiceMetadataDetailView(SecuredDetailView):
    model = ServiceMetadata
    content_type = "application/xml"
    queryset = ServiceMetadata.objects.all().select_related("document").values("document__xml")

    def render_to_response(self, context, **response_kwargs):
        return HttpResponse(content=self.object.document.xml,
                            content_type=self.content_type)


class DatasetMetadataUpdateView(SecuredUpdateView):
    model = DatasetMetadata
    form_class = DatasetMetadataModelForm


class DatasetMetadataRestoreView(SecuredConfirmView):
    model = DatasetMetadata

    def form_valid(self, form):
        self.object.restore()
        return super().form_valid(form=form)


class DatasetMetadataDetailView(RedirectView):
    pattern_name = "resourceNew:dataset_metadata_xml_view"

    def get_redirect_url(self, *args, **kwargs):
        view_kind = self.request.GET.get("vk", None)
        if view_kind:
            if "html" == view_kind:
                # todo
                pass
            elif "xml" == view_kind:
                self.pattern_name = "resourceNew:service_xml_view"
        return super().get_redirect_url(*args, **kwargs)


class DatasetMetadataXmlView(SecuredDetailView):
    model = DatasetMetadata
    queryset = DatasetMetadata.objects.all().select_related("document").values("document__xml")
    content_type = "application/xml"

    def render_to_response(self, context, **response_kwargs):
        return HttpResponse(content=self.object.document.xml,
                            content_type=self.content_type)
