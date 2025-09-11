from django.contrib.gis.db.models.fields import PolygonField
from django.contrib.gis.geos.polygon import Polygon
from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models.expressions import F, OuterRef, Subquery, Value
from django.db.models.fields import BooleanField, FloatField
from django.db.models.functions import Coalesce, JSONObject
from django.db.models.query import Prefetch, Q, QuerySet
from django_cte import with_cte
from extras.utils import get_included_resources, get_sparse_fields
from registry.expressions.layer_ctes import (AncestorsHeritageAggregatedCTE,
                                             AncestorsHeritageCTE,
                                             LayerSecurityInformationCTE)
from registry.models.metadata import (DatasetMetadataRecord, Dimension,
                                      Keyword, ReferenceSystem, Style)


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
        return Dimension.objects.filter(layer__in=self.ancestors_per_layer(layer_attribute="layer__", include_self=True).values("pk")).distinct("name")

    def inherited_styles(self) -> QuerySet:
        return Style.objects.filter(layer__in=self.ancestors_per_layer(layer_attribute="layer__", include_self=True).values("pk")).distinct("name")

    def with_inherited_values(self):
        return self.annotate(
            is_queryable_inherited=self.inherited_is_queryable(),
            is_cascaded_inherited=self.inherited_is_cascaded(),
            is_opaque_inherited=self.inherited_is_opaque(),
            scale_min_inherited=self.inherited_scale_min(),
            scale_max_inherited=self.inherited_scale_max(),
            bbox_lat_lon_inherited=self.inherited_bbox_lat_lon(),
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
            dimensions_inherited=JSONBAgg(
                JSONObject(
                    pk="layer_dimension__pk",
                    name="layer_dimension__name",
                    units="layer_dimension__units",
                    parsed_extent="layer_dimension__parsed_extent",
                ),
                filter=Q(layer_dimension__pk__isnull=False),
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

    def build_cte_and_kwargs(self, cte_cls, cte_fields, sparse_key):
        """
        Baut ein (cte_instance, kwargs)-Tuple dynamisch auf Basis der sparse_fields.

        Args:
            cte_cls: Die CTE-Klasse, z. B. AncestorsHeritageCTE
            cte_fields (list[str]): alle möglichen Felder
            sparse_key (str): Key in sparse_fields, der Filter-Präfixe liefert

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
        cte_instance = cte_cls(fields) if fields else None

        # kwargs dict dynamisch bauen
        annotation_kwargs = (
            {field: getattr(cte_instance.col, field) for field in fields}
            if cte_instance else {}
        )

        return cte_instance, annotation_kwargs

    def get_ancestors_heritage_cte(self):
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
            "Layer"
        )

    def get_ancestors_aggregated_cte(self):
        cte_fields = [
            "reference_systems_inherited",
            "dimensions_inherited",
            "styles_inherited",
        ]
        return self.build_cte_and_kwargs(
            AncestorsHeritageAggregatedCTE,
            cte_fields,
            "Layer"
        )

    def get_security_information_cte(self):
        cte_fields = [
            "is_secured",
            "is_spatial_secured",
        ]
        return self.build_cte_and_kwargs(
            LayerSecurityInformationCTE,
            cte_fields,
            "Layer"
        )

    def with_inherited_attributes_cte(self, request=None):
        self.sparse_fields = get_sparse_fields(request)
        qs = self

        heritage_cte, heritage_annotation_kwargs = self.get_ancestors_heritage_cte()
        if heritage_cte:
            qs = with_cte(
                heritage_cte,
                select=heritage_cte.join(
                    qs,
                    id=heritage_cte.col.id,
                    _join_type="LEFT JOIN"
                )
            )

        aggregated_cte, aggregated_annotation_kwargs = self.get_ancestors_aggregated_cte()
        if aggregated_cte:
            qs = with_cte(
                aggregated_cte,
                select=aggregated_cte.join(
                    qs,
                    id=aggregated_cte.col.id,
                    _join_type="LEFT JOIN"
                )
            )

        security_cte, security_annotation_kwargs = self.get_security_information_cte()
        if security_cte:
            qs = with_cte(
                security_cte,
                select=security_cte.join(
                    qs,
                    id=security_cte.col.layer_id,
                    _join_type="LEFT JOIN"
                )
            )

        qs = qs.annotate(
            **heritage_annotation_kwargs,
            **aggregated_annotation_kwargs,
            **security_annotation_kwargs
        )

        return qs


class LayerPrefetch(Prefetch):

    def get_queryset(self, request=None):
        from registry.models.service import Layer
        sparse_fields = get_sparse_fields(request)
        layer_sparse_fields = sparse_fields.get("Layer", [])
        included_resources = get_included_resources(request)

        prefetch_related = []

        if not layer_sparse_fields or "keywords" in layer_sparse_fields:
            prefetch_related.append(
                Prefetch(
                    "keywords",
                    # TODO: check if layers.keywords are included... then we need an other queryset
                    queryset=Keyword.objects.only("id")
                )
            )

        if not layer_sparse_fields or "dataset_metadata" in layer_sparse_fields:
            prefetch_related.append(
                Prefetch(
                    "registry_datasetmetadatarecord_metadata_records",
                    # TODO: check if layers.datasetMetadata are included... then we need an other queryset
                    queryset=DatasetMetadataRecord.objects.only("id")
                )
            )

        return Layer.objects.with_inherited_attributes_cte(
            request
        ).select_related(
            "mptt_parent",
            "mptt_tree"
        ).prefetch_related(
            *prefetch_related
        )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(
            "layers",
            queryset=self.get_queryset(request),
            *args,
            **kwargs
        )


class RequestBasedPrefetch(Prefetch):
    def __init__(self,

                 lookup,
                 queryset,
                 to_attr,
                 request=None,


                 ):

        super().__init__(lookup, queryset, to_attr)
