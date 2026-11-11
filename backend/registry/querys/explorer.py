"""Opt-in service coverage projections, answered once per page."""
from django.contrib.gis.db.models.aggregates import Union
from django.db.models import Count, OuterRef
from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord
from registry.models.service import CatalogueService, FeatureType, Layer, WebMapService

CATALOGUE_RECORD_MODELS = (DatasetMetadataRecord, ServiceMetadataRecord)


def service_elements(model):
    if model is WebMapService:
        # WMS inherits from ancestors, never from children. Include every layer
        # so a child with an explicit bbox also contributes to service coverage.
        return Layer.objects.annotate(coverage=Layer.objects.inherited_bbox_lat_lon()), 'coverage'
    return FeatureType.objects.all(), 'bbox_lat_lon'


def catalogue_records(model):
    return model.objects.filter(harvested_through=OuterRef('pk')).order_by().values('harvested_through')


def _merge(rows, extents, counts, service_key):
    """Fold one grouped result set into the per-service extents and counts."""
    for row in rows:
        service_id = row[service_key]
        if 'extent' in row:
            geometry = row['extent']
            if geometry is not None:
                current = extents.get(service_id)
                # the rows are read for this merge, so GEOS may union in place
                extents[service_id] = current.union(geometry) if current is not None else geometry
        if 'count' in row:
            counts[service_id] = counts.get(service_id, 0) + row['count']


def _aggregates_map(services, model, extent, element_count):
    """Read the coverage of all given services with one grouped query per source.

    Returns:
        tuple: the extent and the element count per service id; a service
            without elements is absent from both, which answers None and 0
    """
    ids = [service.pk for service in services]
    if model is CatalogueService:
        # the records of a catalogue reach it over the many to many relation
        # of the harvesting, which can repeat a row
        field, key, distinct = 'bounding_geometry', 'harvested_through', True
        sources = [(record_model.objects.filter(harvested_through__in=ids), key)
                   for record_model in CATALOGUE_RECORD_MODELS]
    else:
        elements, field = service_elements(model)
        key, distinct = 'service', False
        sources = [(elements.filter(service__in=ids), key)]

    annotations = {}
    if extent:
        annotations['extent'] = Union(field)
    if element_count:
        annotations['count'] = Count('pk', distinct=distinct)

    extents, counts = {}, {}
    for base, key in sources:
        rows = base.order_by().values(key).annotate(**annotations)
        _merge(rows, extents, counts, key)
    return extents, counts


def service_aggregates(services, model=None, extent=True, element_count=True):
    """Attach the coverage of the given services to their instances.

    The extent and the number of elements of a service are answered from the
    elements of the service. Aggregated as an annotation they ask the database
    per service; aggregated here they ask once for the whole page.

    Args:
        services: the service instances a response answers, e.g. a page
        model: the model of the services, defaults to the class of the first one
        extent (bool): whether to attach the coverage of each service
        element_count (bool): whether to attach its number of elements

    Returns:
        the given services
    """
    services = list(services)
    if not services:
        return services
    model = model or services[0].__class__
    if extent or element_count:
        extents, counts = _aggregates_map(services, model, extent, element_count)
        for service in services:
            if extent:
                service.extent = extents.get(service.pk)
            if element_count:
                service.element_count = counts.get(service.pk, 0)
    return services


class ServiceExplorerMixin:
    """Answer the opt-in coverage attributes from the page, not from the query.

    Both attributes are strictly opt-in, even without a sparse fieldset: a
    request names them in its sparse fields, and only then are they read.
    """

    def _explorer_requested(self, model):
        fields = self.request.GET.get(f'fields[{model.__name__}]', '').split(',')
        return ('extent' in fields,
                'element_count' in fields or 'elementCount' in fields)

    def with_service_aggregates(self, services, model):
        extent, element_count = self._explorer_requested(model)
        return service_aggregates(services, model=model,
                                  extent=extent, element_count=element_count)

    def paginate_queryset(self, queryset, *args, **kwargs):
        page = super().paginate_queryset(queryset, *args, **kwargs)
        if page is not None:
            self.with_service_aggregates(page, queryset.model)
        return page

    def get_object(self):
        instance = super().get_object()
        self.with_service_aggregates([instance], instance.__class__)
        return instance
