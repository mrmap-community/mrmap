from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Value
from django.http import HttpResponse, Http404
from django.views.generic import DetailView

from registry.models import DatasetMetadata, WebMapService, WebFeatureService, Layer, \
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


class WebMapServiceXmlView(GenericXmlRepresentationView):
    model = WebMapService
    queryset = WebMapService.objects.all().annotate(do_camouflage=F('proxy_setting__camouflage'))


class LayerXmlView(GenericXmlRepresentationView):
    model = Layer
    queryset = Layer.objects.all().annotate(do_camouflage=F('service__proxy_setting__camouflage'))


class WebFeatureServiceXmlView(GenericXmlRepresentationView):
    model = WebFeatureService
    queryset = WebFeatureService.objects.all().annotate(do_camouflage=F('proxy_setting__camouflage'))


class FeatureTypeXmlView(GenericXmlRepresentationView):
    model = FeatureType
    queryset = FeatureType.objects.all().annotate(do_camouflage=F('service__proxy_setting__camouflage'))


class WebMapServiceMetadataXmlView(GenericXmlRepresentationView):
    model = WebMapService
    queryset = WebMapService.objects.all().annotate(do_camouflage=F('proxy_setting__camouflage'))


class LayerMetadataXmlView(GenericXmlRepresentationView):
    model = Layer
    queryset = Layer.objects.all().annotate(do_camouflage=F("service__proxy_setting__camouflage"))


class WebFeatureServiceMetadataXmlView(GenericXmlRepresentationView):
    model = WebFeatureService
    queryset = WebFeatureService.objects.all().annotate(do_camouflage=F('proxy_setting__camouflage'))


class FeatureTypeMetadataXmlView(GenericXmlRepresentationView):
    model = FeatureType
    queryset = FeatureType.objects.all().annotate(do_camouflage=F("service__proxy_setting__camouflage"))


class DatasetMetadataXmlView(GenericXmlRepresentationView):
    model = DatasetMetadata
    queryset = DatasetMetadata.objects.all().annotate(do_camouflage=Value(False))
