import re

from django.contrib.gis.db.models import PolygonField
from django.contrib.gis.geos.polygon import Polygon
from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models import (BooleanField, F, FloatField, OuterRef, Prefetch,
                              Q, QuerySet, Subquery, Value)
from django.db.models.functions import Coalesce, JSONObject
from django_cte import with_cte
from extras.utils import get_sparse_fields, undo_format_field_name
from registry.expressions.layer_ctes import (AncestorsHeritageAggregatedCTE,
                                             AncestorsHeritageCTE,
                                             LayerSecurityInformationCTE)
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      ReferenceSystem, Style, TimeExtent)


LEFT_JOIN = "LEFT JOIN"

#: the attributes which :meth:`LayerQuerySet.with_inherited_attributes_cte`
#: answers per layer and which no column of a layer row carries itself
HERITAGE_CTE_FIELDS = (
    "is_queryable_inherited",
    "is_cascaded_inherited",
    "is_opaque_inherited",
    "scale_min_inherited",
    "scale_max_inherited",
    "bbox_lat_lon_inherited",
)
AGGREGATED_CTE_FIELDS = (
    "reference_systems_inherited",
    "time_extents_inherited",
    "styles_inherited",
)
SECURITY_CTE_FIELDS = (
    "is_secured",
    "is_spatial_secured",
)
INHERITED_ATTRIBUTES = (
    HERITAGE_CTE_FIELDS + AGGREGATED_CTE_FIELDS + SECURITY_CTE_FIELDS)


def wanted_inherited_attributes(request=None) -> tuple:
    """The inherited attributes which a request wants answered.

    The rule is the one the CTEs themselves follow in
    :meth:`LayerQuerySet.build_cte_and_kwargs`: a sparse fieldset of the layer
    resource which names none of them answers none of them, and a request
    which names nothing of a resource gets all of them.

    Args:
        request: the request which is answered, optional

    Returns:
        tuple: the names to annotate, empty if the request wants none
    """
    layer_fields = get_sparse_fields(request).get("Layer", [])
    if not layer_fields:
        return INHERITED_ATTRIBUTES
    return tuple(
        field for field in INHERITED_ATTRIBUTES
        if any(field.startswith(prefix) for prefix in layer_fields))


#: a ``filter[...]`` query parameter of the json:api style
FILTER_PARAMETER = re.compile(r"^filter\[(?P<name>[^\]]+)\]$")


def _orm_name(name: str) -> str:
    """The name of the ORM behind the name a json:api request writes.

    The json:api backend turns a dotted relationship path into the ``__``
    notation of the ORM and undoes the field name format of the api before a
    filterset or an ordering filter is asked for the name.

    Args:
        name (str): the name as the api writes it

    Returns:
        str: the name as the database is asked with it
    """
    return undo_format_field_name(name.replace('.', '__'))


def reads_inherited_attributes(field_name: str) -> bool:
    """Whether a field path is answered by the derivation of the CTEs.

    Args:
        field_name (str): the field path a condition is asked with, which may
            carry a lookup suffix

    Returns:
        bool: True if the path names one of the annotated attributes, or a
            lookup of one of them
    """
    return (field_name in INHERITED_ATTRIBUTES
            or field_name.rsplit('__', 1)[0] in INHERITED_ATTRIBUTES)


def filters_on_inherited_attributes(filterset_class) -> frozenset:
    """The names of the filters which read the derivation of the CTEs.

    A filterset names a filter by its own key and points it at an annotation
    with ``field_name``, so the key of ``filter[...]`` of a request has to be
    looked up in the filterset to know whether it asks the database about an
    inherited attribute: ``bbox_lat_lon__contains`` of ``LayerFilterSet``
    filters on ``bbox_lat_lon_inherited``.

    Args:
        filterset_class: the filterset of the endpoint, may be ``None``

    Returns:
        frozenset: the filter names which read the derivation
    """
    base_filters = getattr(filterset_class, 'base_filters', None) or {}
    return frozenset(
        name for name, declared in base_filters.items()
        if reads_inherited_attributes(
            getattr(declared, 'field_name', None) or name))


def inherited_attributes_are_a_condition(request, filterset_class=None) -> bool:
    """Whether a request asks the database *about* the inherited attributes.

    A request which only *shows* the inherited attributes needs them for the
    rows it shows, which :func:`answer_page_inherited_attributes` answers for
    its page. A request which *narrows or orders its rows by* one of them
    needs them inside its own statement, because the condition decides the
    rows before any page exists and can only be asked of rows the statement
    already selects: the bbox filters of ``LayerFilterSet`` read the annotation
    of a CTE, and a sort would read it the same way. Such a request keeps the
    derivation in its statement - the condition is the meaning of the request,
    and it is asked once over the whole filtered set rather than per row, as
    ``filter[has_alert]`` already does (#1424).

    Args:
        request: the request which is answered
        filterset_class: the filterset of the endpoint, optional

    Returns:
        bool: True if the statement of the request has to answer the
            derivation itself
    """
    if request is None or not hasattr(request, 'GET'):
        return False
    derivation_filters = filters_on_inherited_attributes(filterset_class)
    if any(_orm_name(FILTER_PARAMETER.match(key).group('name'))
           in derivation_filters
           for key in request.GET if FILTER_PARAMETER.match(key)):
        return True
    return any(
        reads_inherited_attributes(_orm_name(term.strip().lstrip('-')))
        for term in str(request.GET.get('sort', '')).split(',') if term.strip())


def answer_page_inherited_attributes(layers, request=None,
                                     filterset_class=None):
    """Answer the inherited attributes on the rows of a page read without them.

    The counterpart of reading a list without the derivation: a CTE answers one
    row for every layer the statement selects, and the statement of a page
    selects every layer its filters keep - not only the rows it shows - so the
    25-row page of the flat list derived the effective values of all 141,240
    layers of the deployment to show 25 of them (#1825). Here the same CTEs
    answer the attributes of exactly the layers of the page - one statement
    over their identifiers, bounded by the page size instead of by the layer
    table - and the answers land on the rows the page already holds, so the
    serializers read the very attributes they always read.

    The read plan is the one ``registry/querys/alerts.py`` established for the
    alerts of a service (#1424); the values are the ones #1315 defines: the
    scope of a CTE only decides for how many layers it answers, never which
    value a layer gets, because the ancestry of a layer is looked up in every
    layer of the registry.

    A no-op for a page whose statement answered the derivation itself (a
    request whose filter or sort names one of the attributes) and for a page
    which shows nothing of it (a sparse fieldset which names none), so that no
    request pays the derivation twice and none pays it for nothing.

    Args:
        layers (list): the layers of a page, read without their derivation
        request: the request which is answered, for its sparse fieldsets
        filterset_class: the filterset of the endpoint, to tell a filter which
            reads the derivation apart from one which does not
    """
    if not layers or inherited_attributes_are_a_condition(
            request, filterset_class):
        return
    answered = wanted_inherited_attributes(request)
    if not answered:
        return
    answers = {
        row.pk: row
        for row in type(layers[0])._default_manager.filter(
            pk__in=[layer.pk for layer in layers]
        ).with_inherited_attributes_cte(request)}
    for layer in layers:
        answer = answers[layer.pk]
        for name in answered:
            setattr(layer, name, getattr(answer, name, None))


class LayerQuerySet(QuerySet):
    sparse_fields = {}

    def _inherited_field(
        self,
        field_name: str,
        default=None,
        include_self: bool = True,
        exclude_values=None,
        output_field=None,
    ):
        """Generischer Helper für geerbte Felder."""
        qs = self.ancestors_per_layer(include_self=include_self)
        if exclude_values is not None:
            qs = qs.exclude(**{field_name + "__in": exclude_values})

        return Coalesce(
            F(field_name),
            Subquery(qs.values_list(field_name, flat=True)
                     [:1], output_field=output_field),
            Value(default),
            output_field=output_field
        )

    def ancestors_per_layer(self, layer_attribute: str = "", include_self: bool = False):
        return self.filter(
            mptt_tree=OuterRef(f"{layer_attribute}mptt_tree"),
            mptt_lft__lte=OuterRef(f"{layer_attribute}mptt_lft") if include_self else OuterRef(
                f"{layer_attribute}mptt_lft") - 1,
            mptt_rgt__gte=OuterRef(
                f"{layer_attribute}mptt_rgt") if include_self else OuterRef(f"{layer_attribute}mptt_rgt") + 1
        )

    def inherited_is_queryable(self) -> bool:
        return self._inherited_field("is_queryable", default=False, exclude_values=[False], output_field=BooleanField())

    def inherited_is_cascaded(self) -> bool:
        return self._inherited_field("is_cascaded", default=False, exclude_values=[False], output_field=BooleanField())

    def inherited_is_opaque(self) -> bool:
        return self._inherited_field("is_opaque", default=False, exclude_values=[False], output_field=BooleanField())

    def inherited_scale_min(self) -> int:
        """Return the scale min value of this layer based on the inheritance from other layers as requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: ScaleHint is inherited by child Layers.  A ScaleHint declaration in the child replaces the
             any declaration inherited from the parent. (see section 7.1.4.5.8 ScaleHint)


        :return: self.scale_min if not None else scale_min from the first ancestors where scale_min is not None
        :rtype: :class:`django.contrib.gis.geos.polygon`
        """
        return self._inherited_field("scale_min", default=None, output_field=FloatField())

    def inherited_scale_max(self) -> int:
        """Return the scale max value of this layer based on the inheritance from other layers as requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: ScaleHint is inherited by child Layers.  A ScaleHint declaration in the child replaces the
             any declaration inherited from the parent. (see section 7.1.4.5.8 ScaleHint)


        :return: self.scale_max if not None else scale_max from the first ancestors where scale_max is not None
        :rtype: :class:`django.contrib.gis.geos.polygon`
        """
        return self._inherited_field("scale_max", default=None, output_field=FloatField())

    def inherited_bbox_lat_lon(self) -> Polygon:
        """Return the bbox of this layer based on the inheritance from other layers as requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: Every Layer shall have exactly one <LatLonBoundingBox> element that is either stated
             explicitly or inherited from a parent Layer. (see section 7.1.4.5.6)
           * **ogc wms 1.3.0**: Every named Layer shall have exactly one <EX_GeographicBoundingBox> element that is
             either stated explicitly or inherited from a parent Layer. (see section 7.2.4.6.6)


        :return: self.bbox_lat_lon if not None else bbox_lat_lon from the first ancestors where bbox_lat_lon is not None
        :rtype: :class:`django.contrib.gis.geos.polygon`
        """
        return self._inherited_field("bbox_lat_lon", default=None, output_field=PolygonField())

    def inherited_reference_systems(self) -> QuerySet:
        """Return all supported reference systems for this layer, based on the inheritance from other layers as
        requested in the ogc specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: Every Layer shall have at least one <SRS> element that is either stated explicitly or
             inherited from a parent Layer (see section 7.1.4.5.5).
           * **ogc wms 1.3.0**: Every Layer is available in one or more layer coordinate reference systems. 6.7.3
             discusses the Layer CRS. In order to indicate which Layer CRSs are available, every named Layer shall have
             at least one <CRS> element that is either stated explicitly or inherited from a parent Layer.

        :return: all supported reference systems :class:`registry.models.metadata.ReferenceSystem` for this layer
        :rtype: :class:`django.db.models.query.QuerySet`
        """
        return ReferenceSystem.objects.filter(layer__in=self.ancestors_per_layer(layer_attribute="layer__", include_self=True).values("pk")).distinct(
            "code", "prefix")

    def inherited_dimensions(self) -> QuerySet:
        """Return all dimensions of this layer, based on the inheritance from other layers as requested in the ogc
        specs.

        .. note:: excerpt from ogc specs

           * **ogc wms 1.1.1**: Dimension declarations are inherited from parent Layers. Any new Dimension declarations
             in the child are added to the list inherited from the parent. A child **shall not** redefine a  Dimension
             with the same name attribute as one that was inherited. Extent declarations are inherited from parent
             Layers. Any Extent declarations in the child with the same name attribute as one inherited from the parent
             replaces the value declared by the parent.  A Layer shall not declare an Extent unless a Dimension with the
             same name has been declared or inherited earlier in the Capabilities XML.

           * **ogc wms 1.3.0**: Dimension  declarations  are  inherited  from  parent  Layers.  Any  new  Dimension
             declaration  in  the  child  with  the  same name attribute as one inherited from the parent replaces the
             value declared by the parent.


        :return: all dimensions of this layer
        :rtype: :class:`django.db.models.query.QuerySet`
        """
        return TimeExtent.objects.filter(layer__in=self.ancestors_per_layer(layer_attribute="layer__", include_self=True).values("pk")).distinct("name")

    def inherited_styles(self) -> QuerySet:
        return Style.objects.filter(layer__in=self.ancestors_per_layer(layer_attribute="layer__", include_self=True).values("pk")).distinct("name")

    def with_inherited_values(self):
        # The ancestry of a layer is looked up in every layer of the registry and
        # not in `self`: which value a layer inherits only depends on the layers
        # on its own path, while `self` may already be narrowed to the layers the
        # effective values are answered for (#1315).
        registry = self.model._default_manager.all()
        return self.annotate(
            is_queryable_inherited=registry.inherited_is_queryable(),
            is_cascaded_inherited=registry.inherited_is_cascaded(),
            is_opaque_inherited=registry.inherited_is_opaque(),
            scale_min_inherited=registry.inherited_scale_min(),
            scale_max_inherited=registry.inherited_scale_max(),
            bbox_lat_lon_inherited=registry.inherited_bbox_lat_lon(),
        )

    def with_aggregated_inherited_values(self):
        return self.annotate(
            reference_systems_inherited=JSONBAgg(
                JSONObject(
                    pk="reference_systems__pk",
                    code="reference_systems__code",
                    prefix="reference_systems__prefix",
                ),
                filter=Q(reference_systems__pk__isnull=False),
                distinct=True,
                default=Value('[]'),
            ),
            time_extents_inherited=JSONBAgg(
                JSONObject(
                    pk="time_extents__pk",
                ),
                filter=Q(time_extents__pk__isnull=False),
                distinct=True,
                default=Value('[]'),
            ),
            styles_inherited=JSONBAgg(
                JSONObject(
                    pk="style__pk",
                    name="style__name",
                    title="style__title"),
                filter=Q(style__pk__isnull=False),
                distinct=True,
                default=Value('[]'),
            )
        )

    def build_cte_and_kwargs(self, cte_cls, cte_fields, sparse_key, scope=None):
        """
        Baut ein (cte_instance, kwargs)-Tuple dynamisch auf Basis der sparse_fields.

        Args:
            cte_cls: Die CTE-Klasse, z. B. AncestorsHeritageCTE
            cte_fields (list[str]): alle möglichen Felder
            sparse_key (str): Key in sparse_fields, der Filter-Präfixe liefert
            scope (QuerySet): ids der Ebenen, für die die CTE antwortet

        Returns:
            tuple: (cte_instance oder None, annotation_kwargs dict)
        """
        layer_fields = self.sparse_fields.get(sparse_key, [])

        # Bestimme die Felder
        if not layer_fields:
            fields = cte_fields
        else:
            fields = [
                field for field in cte_fields
                if any(field.startswith(prefix) for prefix in layer_fields)
            ]

        # Erzeuge die CTE-Instanz nur wenn Felder da sind
        cte_instance = cte_cls(fields, scope=scope) if fields else None

        # kwargs dict dynamisch bauen
        annotation_kwargs = (
            {field: getattr(cte_instance.col, field) for field in fields}
            if cte_instance else {}
        )

        return cte_instance, annotation_kwargs

    def get_ancestors_heritage_cte(self, scope=None):
        cte_fields = [
            "is_queryable_inherited",
            "is_cascaded_inherited",
            "is_opaque_inherited",
            "scale_min_inherited",
            "scale_max_inherited",
            "bbox_lat_lon_inherited",
        ]
        return self.build_cte_and_kwargs(
            AncestorsHeritageCTE,
            cte_fields,
            "Layer",
            scope=scope
        )

    def get_ancestors_aggregated_cte(self, scope=None):
        cte_fields = [
            "reference_systems_inherited",
            "time_extents_inherited",
            "styles_inherited",
        ]
        return self.build_cte_and_kwargs(
            AncestorsHeritageAggregatedCTE,
            cte_fields,
            "Layer",
            scope=scope
        )

    def get_security_information_cte(self, scope=None):
        cte_fields = [
            "is_secured",
            "is_spatial_secured",
        ]
        return self.build_cte_and_kwargs(
            LayerSecurityInformationCTE,
            cte_fields,
            "Layer",
            scope=scope
        )

    def with_inherited_attributes_cte(self, request=None):
        """Annotates the effective values of the inherited attributes.

        Every one of the three CTEs answers one row per layer, so they answer the
        layers which this queryset selects and not every layer of the registry
        (#1315): the layers tab of a WMS with 4 layers used to materialise the
        effective values of all 265,653 layers of the deployment - six correlated
        ancestor probes per layer - and threw all but four of them away on the
        join. That CTE was the request: 48.5 s of its 49.3 s on an idle database.

        The scope is built from this queryset without its annotations, joins and
        order, because only the layers it selects matter; the ancestry of a layer
        is still looked up in all layers, see :meth:`with_inherited_values`.
        """
        self.sparse_fields = get_sparse_fields(request)
        qs = self
        scope = self.select_related(None).order_by().values("pk")

        heritage_cte, heritage_annotation_kwargs = self.get_ancestors_heritage_cte(
            scope=scope)
        if heritage_cte:
            qs = with_cte(
                heritage_cte,
                select=heritage_cte.join(
                    qs,
                    id=heritage_cte.col.id,
                    _join_type=LEFT_JOIN
                )
            )

        aggregated_cte, aggregated_annotation_kwargs = self.get_ancestors_aggregated_cte(
            scope=scope)
        if aggregated_cte:
            qs = with_cte(
                aggregated_cte,
                select=aggregated_cte.join(
                    qs,
                    id=aggregated_cte.col.id,
                    _join_type=LEFT_JOIN
                )
            )

        security_cte, security_annotation_kwargs = self.get_security_information_cte(
            scope=scope)
        if security_cte:
            qs = with_cte(
                security_cte,
                select=security_cte.join(
                    qs,
                    id=security_cte.col.layer_id,
                    _join_type=LEFT_JOIN
                )
            )

        qs = qs.annotate(
            **heritage_annotation_kwargs,
            **aggregated_annotation_kwargs,
            **security_annotation_kwargs
        )

        # The security CTE has no row for an element without configured rules.
        return qs.annotate(**{
            field: Coalesce(F(field), Value(False))
            for field in security_annotation_kwargs
        })


class LayerPrefetch(Prefetch):
    def __init__(self, request=None, to_attr=None):
        super().__init__("layers", queryset=self.get_queryset(request), to_attr=to_attr)

    def get_queryset(self, request=None):
        from registry.models.service import Layer
        sparse_fields = get_sparse_fields(request)
        layer_sparse_fields = sparse_fields.get("Layer", [])

        prefetch_related = []

        if not layer_sparse_fields or "keywords" in layer_sparse_fields:
            prefetch_related.append(
                Prefetch(
                    "keywords",
                    # FUTURE: check if layers.keywords are included... then we need an other queryset
                    queryset=Keyword.objects.only("id")
                )
            )

        if not layer_sparse_fields or "dataset_metadata" in layer_sparse_fields:
            prefetch_related.append(
                Prefetch(
                    "registry_datasetmetadatarecord_metadata_records",
                    # FUTURE: check if layers.datasetMetadata are included... then we need an other queryset
                    queryset=DatasetMetadataRecord.objects.only("id")
                )
            )
        # with_inherited_attributes_cte is only needed if any inherited attribute is requested.
        qs = Layer.objects.with_inherited_attributes_cte(
            request
        ).select_related(
            "mptt_parent",
            "mptt_tree"
        ).prefetch_related(
            *prefetch_related
        )

        return qs
