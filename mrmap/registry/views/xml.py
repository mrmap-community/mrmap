from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Value
from django.http import HttpResponse, Http404
from django.views.generic import DetailView

from registry.models import DatasetMetadata, ServiceMetadata, LayerMetadata, FeatureTypeMetadata, Service, Layer, \
    FeatureType


class GenericXmlRepresentationView(DetailView):
    content_type = "application/xml"

    def render_to_response(self, context, **response_kwargs):
        try:
            if self.object.do_camouflage:
                doc = self.object.document.xml_secured(request=self.request)
            else:
                doc = self.object.xml
        except ObjectDoesNotExist:
            raise Http404("No xml representation was found for this service metadata.")
        return HttpResponse(content=doc.serializeDocument(),
                            content_type=self.content_type)


class ServiceXmlView(GenericXmlRepresentationView):
    model = Service
    queryset = Service.objects.all().annotate(do_camouflage=F('proxy_setting__camouflage'))


class LayerXmlView(GenericXmlRepresentationView):
    model = Layer
    queryset = Layer.objects.all().annotate(do_camouflage=F('service__proxy_setting__camouflage'))


class FeatureTypeXmlView(GenericXmlRepresentationView):
    model = FeatureType
    queryset = FeatureType.objects.all().annotate(do_camouflage=F('service__proxy_setting__camouflage'))


class ServiceMetadataXmlView(GenericXmlRepresentationView):
    model = Service
    queryset = Service.objects.all().annotate(do_camouflage=F('proxy_setting__camouflage'))


class LayerMetadataXmlView(GenericXmlRepresentationView):
    model = LayerMetadata
    queryset = LayerMetadata.objects.all().annotate(do_camouflage=F("described_object__service__proxy_setting__camouflage"))


class FeatureTypeMetadataXmlView(GenericXmlRepresentationView):
    model = FeatureTypeMetadata
    queryset = FeatureTypeMetadata.objects.all().annotate(do_camouflage=F("described_object__service__proxy_setting__camouflage"))


class DatasetMetadataXmlView(GenericXmlRepresentationView):
    model = DatasetMetadata
    queryset = DatasetMetadata.objects.all().annotate(do_camouflage=Value(False))
