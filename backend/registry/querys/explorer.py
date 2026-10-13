"""Opt-in service coverage projections, evaluated in the page query."""
from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.db.models.aggregates import Union
from django.contrib.gis.db.models.functions import Union as GeometryUnion
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord
from registry.models.service import CatalogueService, FeatureType, Layer, WebMapService


def service_elements(model):
    if model is WebMapService:
        # WMS inherits from ancestors, never from children. Include every layer
        # so a child with an explicit bbox also contributes to service coverage.
        return Layer.objects.annotate(coverage=Layer.objects.inherited_bbox_lat_lon()), 'coverage'
    return FeatureType.objects.all(), 'bbox_lat_lon'


def catalogue_records(model):
    return model.objects.filter(harvested_through=OuterRef('pk')).order_by().values('harvested_through')


def service_coverage(qs):
    if qs.model is CatalogueService:
        extents = [Subquery(catalogue_records(model).annotate(
            extent=Union('bounding_geometry')).values('extent'), output_field=GeometryField(srid=4326))
            for model in (DatasetMetadataRecord, ServiceMetadataRecord)]
        return qs.annotate(extent=Coalesce(GeometryUnion(*extents), *extents))
    elements, field = service_elements(qs.model)
    extent = elements.filter(service=OuterRef('pk')).order_by().values('service').annotate(extent=Union(field)).values('extent')
    return qs.annotate(extent=Subquery(extent, output_field=GeometryField(srid=4326)))


class ServiceExplorerMixin:
    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        # These new attributes are strictly opt-in, even without a sparse set.
        fields = self.request.GET.get(f'fields[{qs.model.__name__}]', '').split(',')
        if 'extent' in fields:
            qs = service_coverage(qs)
        if 'element_count' in fields or 'elementCount' in fields:
            if qs.model is CatalogueService:
                counts = [Subquery(catalogue_records(model).annotate(count=Count('pk', distinct=True)).values('count'))
                          for model in (DatasetMetadataRecord, ServiceMetadataRecord)]
                qs = qs.annotate(element_count=Coalesce(counts[0], 0) + Coalesce(counts[1], 0))
            else:
                elements, _ = service_elements(qs.model)
                count = elements.filter(service=OuterRef('pk')).order_by().values('service').annotate(count=Count('pk')).values('count')
                qs = qs.annotate(element_count=Coalesce(Subquery(count), 0))
        return qs
