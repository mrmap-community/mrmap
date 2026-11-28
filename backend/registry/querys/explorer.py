"""Opt-in service coverage projections, answered once per page.

The extent and the number of elements of a service, and the number of records a
harvesting pulled for a catalogue, all aggregate rows which hang below the
service: the layers of a map service, the feature types of a feature service,
the metadata records which the harvesting of a catalogue collected. Aggregated
as an annotation of the page they answer their derivation once per row the
statement reads, so the cost of a page grows with the volume below the rows it
happens to show and not with the number of rows it shows: a page of twelve
catalogues cost more than a page of two hundred thousand historical records
(#1031), because one catalogue of them held a quarter of a million harvest
relations (#1826).

Answered here they ask one grouped statement per source over the identifiers of
the page, bounded by the page size instead of by the table below the service.

Nothing of this is answered to a request which does not ask for it. As with the
alerts of `registry/querys/alerts.py`, an answer is given when the sparse
fieldset of the request names it, or - for the counters of a harvesting - when
the request is the detail of the resource, which answers all of its attributes.
A list which names none of them reads none of the rows behind them, so the
default list of a resource is not the most expensive variant of the route.
"""
from camel_converter import to_camel
from django.contrib.gis.db.models.aggregates import Union
from django.db.models import Count
from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord
from registry.models.service import CatalogueService, FeatureType, Layer, WebMapService

CATALOGUE_RECORD_MODELS = (DatasetMetadataRecord, ServiceMetadataRecord)

#: the name of the relation which connects a metadata record to the catalogue
#: which harvested it; the join table of the relation is what counts its records
HARVESTED_THROUGH = 'harvested_through'

#: the counters which answer how many records a harvesting pulled for a catalogue
HARVEST_COUNT_ATTRIBUTES = ('harvested_dataset_count', 'harvested_service_count',
                            'harvested_total_count')

#: the kinds of record a harvesting pulls into the registry, in the order of
#: the two partial counters which answer their number
HARVEST_KINDS = ('dataset', 'service')

#: the counter of each kind of record a harvesting pulls into the registry
HARVEST_COUNT_OF_KIND = tuple(zip(HARVEST_COUNT_ATTRIBUTES[:2], HARVEST_KINDS))


def service_elements(model):
    if model is WebMapService:
        # WMS inherits from ancestors, never from children. Include every layer
        # so a child with an explicit bbox also contributes to service coverage.
        return Layer.objects.annotate(coverage=Layer.objects.inherited_bbox_lat_lon()), 'coverage'
    return FeatureType.objects.all(), 'bbox_lat_lon'


def catalogue_record_counts(ids, kinds=None) -> dict:
    """Count the records which a harvesting pulled for each given catalogue.

    The records of a catalogue reach it over the many to many relation of the
    harvesting, so the records of a catalogue are the rows of its join table
    which name that catalogue: one grouped statement per kind of record, keyed
    by the catalogue and restricted to the identifiers asked for, reads the join
    column the database indexes. The pair of a record and a catalogue lives once
    in that table, so the rows of a group are its records and the count needs no
    distinct - the distinct of the correlated aggregate of the page query is what
    made a heavily harvested catalogue cost half a second on its own (#1826). No
    geometry is read either, which is what keeps the number affordable where the
    extent of the same records is not.

    Args:
        ids: the identifiers of the catalogues to count records for
        kinds (dict): which kinds to read, as `harvest_kinds_to_read()` answers
            them; every kind is read when omitted

    Returns:
        dict: the number of records per kind and catalogue, a kind being
            ``dataset`` or ``service``; a catalogue without records of a kind is
            absent from its kind, which answers nothing and not zero
    """
    return {
        kind: dict(
            model.objects.filter(**{f'{HARVESTED_THROUGH}__in': ids})
            .order_by()
            .values(HARVESTED_THROUGH)
            .annotate(count=Count('pk'))
            .values_list(HARVESTED_THROUGH, 'count'))
        for model, kind in zip(CATALOGUE_RECORD_MODELS, HARVEST_KINDS)
        if kinds is None or kinds.get(kind)}


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

    The records of a catalogue are counted apart from its coverage by
    `catalogue_record_counts()`, which needs neither a geometry nor a join of two
    tables: a request which asks their number but not their extent asks nothing
    of this function (#1826).

    Neither aggregation needs a distinct. Every source groups the rows of one
    table by the column which names its service - a layer, a feature type or a
    metadata record - and each of those rows belongs to one service and is read
    once, which is what the ``COUNT(DISTINCT ...)`` of the correlated aggregate
    of the page query answered redundantly, once per row (#1826).

    Returns:
        tuple: the extent and the element count per service id; a service
            without elements is absent from both, which answers None and 0
    """
    ids = [service.pk for service in services]
    if model is CatalogueService:
        # the records of a catalogue reach it over the many to many relation of
        # the harvesting, so the group column is the one of its join table
        field, key = 'bounding_geometry', HARVESTED_THROUGH
        sources = [(record_model.objects.filter(**{f'{HARVESTED_THROUGH}__in': ids}), key)
                   for record_model in CATALOGUE_RECORD_MODELS]
    else:
        elements, field = service_elements(model)
        key = 'service'
        sources = [(elements.filter(service__in=ids), key)]

    annotations = {}
    if extent:
        annotations['extent'] = Union(field)
    if element_count:
        annotations['count'] = Count('pk')

    extents, counts = {}, {}
    for base, key in sources:
        rows = base.order_by().values(key).annotate(**annotations)
        _merge(rows, extents, counts, key)
    return extents, counts


def _kinds_to_read(element_count: bool, harvest_counts: dict) -> dict:
    """Which kinds of record of a catalogue must be read for what is asked.

    The element count of a catalogue is the number of all its records, so it
    needs both kinds; a counter of the harvesting needs only its own kind.
    """
    needed = harvest_kinds_to_read(harvest_counts)
    return {kind: element_count or needed[kind] for kind in HARVEST_KINDS}


def _records_of(per_kind: dict, service_pk) -> int:
    """The number of records of one catalogue over every kind which was read."""
    return sum(kind.get(service_pk, 0) for kind in per_kind.values())


def _attach_coverage(service, extent, element_count, catalogue, extents, counts,
                     per_kind) -> None:
    """Attach the coverage attributes which the request asked for.

    The number of the records of a catalogue comes from `catalogue_record_counts()`,
    never from the statement of its coverage: the coverage aggregation reads
    geometries and must stay free of the count, which is pinned by the tests of
    #1031.
    """
    if extent:
        service.extent = extents.get(service.pk)
    if element_count:
        service.element_count = (_records_of(per_kind, service.pk)
                                 if catalogue else counts.get(service.pk, 0))


def _attach_harvest_counters(service, harvest_counts: dict, per_kind: dict) -> None:
    """Attach the counters of the harvesting which the request named."""
    if harvest_counts.get('harvested_total_count'):
        service.harvested_total_count = _records_of(per_kind, service.pk)
    for name, kind in HARVEST_COUNT_OF_KIND:
        if harvest_counts.get(name):
            setattr(service, name, per_kind.get(kind, {}).get(service.pk, 0))


def service_aggregates(services, model=None, extent=True, element_count=True,
                       harvest_counts=None):
    """Attach the coverage and the harvest counters of the given services.

    The extent and the number of elements of a service are answered from the
    elements of the service. Aggregated as an annotation they ask the database
    per service; aggregated here they ask once for the whole page. The counters
    of the harvesting of a catalogue count the very records its element count
    counts, so one grouped read over both kinds of record answers them all.

    Args:
        services: the service instances a response answers, e.g. a page
        model: the model of the services, defaults to the class of the first one
        extent (bool): whether to attach the coverage of each service
        element_count (bool): whether to attach its number of elements
        harvest_counts (dict): which counters of the harvesting to attach to a
            catalogue, as `harvest_counts_requested()` answers them

    Returns:
        the given services
    """
    services = list(services)
    if not services:
        return services
    model = model or services[0].__class__
    harvest_counts = harvest_counts or {}
    catalogue = model is CatalogueService
    kinds = _kinds_to_read(element_count, harvest_counts) if catalogue else {}
    # the element count of a catalogue and the counters of its harvesting count
    # the same rows, so they share one grouped read over both kinds of record
    per_kind = (catalogue_record_counts([service.pk for service in services], kinds)
                if catalogue and any(kinds.values()) else {})
    coverage_count = element_count and not catalogue
    if extent or coverage_count:
        extents, counts = _aggregates_map(services, model, extent, coverage_count)
    else:
        extents, counts = {}, {}
    counters_asked = any(harvest_counts.values())
    for service in services:
        _attach_coverage(service, extent, element_count, catalogue,
                         extents, counts, per_kind)
        if counters_asked:
            _attach_harvest_counters(service, harvest_counts, per_kind)
    return services


def answer_harvest_counts(catalogues, requested=None) -> list:
    """Attach the counters of the harvesting to the given catalogues.

    The counterpart of `registry/querys/alerts.answer_page_alerts()` for the
    records which a harvesting pulled for a catalogue: the statement of the page
    reads its rows without them, and they are answered here for exactly the rows
    of the page.

    Args:
        catalogues: the catalogue instances a response answers, e.g. a page
        requested (dict): which counters to answer, as `harvest_counts_requested()`
            answers them; all of them answer by default

    Returns:
        the given catalogues
    """
    catalogues = list(catalogues)
    if not catalogues:
        return catalogues
    if requested is None:
        requested = dict.fromkeys(HARVEST_COUNT_ATTRIBUTES, True)
    return service_aggregates(catalogues, model=CatalogueService, extent=False,
                              element_count=False, harvest_counts=requested)


def harvest_counts_requested(request, resource: str,
                             list_view: bool = False) -> dict:
    """Whether a request wants the counters of the harvesting of a catalogue.

    The counters count the records which a harvesting pulled for a catalogue,
    which for a heavily harvested one is the most expensive answer the resource
    has. They are therefore answered by the very rule the alerts of
    `registry/querys/alerts.py` follow: to a request which names them in its
    sparse fieldset, or to the detail of a catalogue, which answers all of its
    attributes. Nothing of this is asked by a list of catalogues - the shipped
    one shows the failures of the harvesting and the number of elements, but the
    number of published records belongs to the detail card of a catalogue - so a
    list which names none of them pays for none of them (#1826).

    Args:
        request: the request which is answered
        resource (str): name of the resource the request answers
        list_view (bool): whether the request answers a list of the resource

    Returns:
        dict: the counters to answer, keyed as the attributes are named
    """
    fields = request.GET.get(f'fields[{resource}]')
    if fields is None:
        # no sparse fieldset for the resource: only the detail answers the
        # attributes nobody named, as `answers_allowed_actions()` of #738 does
        return dict.fromkeys(HARVEST_COUNT_ATTRIBUTES, not list_view)
    asked = {name.strip() for name in fields.split(',') if name.strip()}
    return {
        attribute: bool(asked & {attribute, to_camel(attribute)})
        for attribute in HARVEST_COUNT_ATTRIBUTES}


def harvest_kinds_to_read(requested: dict) -> dict:
    """Whether a kind of record must be read to answer the requested counters.

    ``harvested_total_count`` is the sum of the two partial counters, so a
    request which names the total reads both kinds of record even when it names
    neither of them; a request which names only a partial counter reads only its
    kind.
    """
    total = requested.get('harvested_total_count')
    return {
        kind: total or bool(requested.get(name))
        for name, kind in HARVEST_COUNT_OF_KIND}


class ServiceExplorerMixin:
    """Answer the opt-in coverage attributes from the page, not from the query.

    The extent and the number of elements are strictly opt-in, even without a
    sparse fieldset: a request names them in its sparse fields, and only then are
    they read. The counters of the harvesting of a catalogue follow the same rule
    with the tolerance of the alerts: the detail of a catalogue answers them
    unasked, because the detail card of a catalogue shows how many records it
    holds, while a list which does not name them shows none of them.
    """

    def _explorer_requested(self, model):
        fields = self.request.GET.get(f'fields[{model.__name__}]', '').split(',')
        return ('extent' in fields,
                'element_count' in fields or 'elementCount' in fields)

    def _harvest_counts_of(self, model, page) -> dict:
        """Which counters of the harvesting the request wants from the page.

        ``list_view`` asks whether the response answers a list of catalogues: the
        nested list of the catalogues behind a metadata record is not a catalogue
        list of its own, even though the outer view answers a list.
        """
        return harvest_counts_requested(
            self.request, model.__name__,
            list_view=getattr(self, 'action', None) == 'list'
            and any(isinstance(service, CatalogueService) for service in page))

    def harvest_counts_answered(self, model) -> dict:
        """The counters this view answered for rows of ``model``.

        The read of the page is the only place which decides, and the serializer
        renders exactly what it decided: a representation which answered a
        counter whose value was never read would read an attribute the instance
        does not carry.
        """
        return getattr(self, '_harvest_counts_answered', {}).get(model, {})

    def with_service_aggregates(self, services, model):
        extent, element_count = self._explorer_requested(model)
        requested = (self._harvest_counts_of(model, services)
                     if model is CatalogueService else {})
        self._harvest_counts_answered = {
            **getattr(self, '_harvest_counts_answered', {}), model: requested}
        return service_aggregates(
            services, model=model, extent=extent, element_count=element_count,
            harvest_counts=requested)

    def paginate_queryset(self, queryset, *args, **kwargs):
        page = super().paginate_queryset(queryset, *args, **kwargs)
        if page is not None:
            self.with_service_aggregates(page, queryset.model)
        return page

    def get_object(self):
        instance = super().get_object()
        self.with_service_aggregates([instance], instance.__class__)
        return instance
