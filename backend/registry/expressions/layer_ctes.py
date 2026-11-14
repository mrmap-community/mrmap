from django.contrib.postgres.aggregates.general import BoolOr
from django.db.models.expressions import F, Value
from django.db.models.query_utils import Q
from django_cte import CTE


class LayerSecurityInformationCTE(CTE):
    """Security information of layers, answered per layer.

    :param values: the annotated names of the security information to answer
    :param scope: queryset of the ids of the layers the information is answered
        for. The aggregation groups by layer, so it answers the same values for
        every layer of the scope and simply does not read the operations which
        belong to layers nobody asked for (#1315). Without a scope the
        information of every secured layer of the registry is aggregated.
    """

    def __init__(self,
                 values=[
                     "is_secured",
                     "is_spatial_secured"
                 ],
                 scope=None,
                 *args,
                 **kwargs):
        from registry.models.security import AllowedWebMapServiceOperation
        operations = AllowedWebMapServiceOperation.objects
        if scope is not None:
            operations = operations.filter(secured_layers__pk__in=scope)
        super(LayerSecurityInformationCTE, self).__init__(
            queryset=operations.annotate(
                layer_id=F("secured_layers__id")
            )
            .values("layer_id")
            .annotate(
                is_secured=BoolOr(Value(True)),
                is_spatial_secured=BoolOr(Q(allowed_area__isnull=False)),
            )
            .values("layer_id", *values),
            name="layer_security_information",
            *args,
            **kwargs
        )


class AncestorsHeritageCTE(CTE):
    """The effective values of the inherited attributes, answered per layer.

    :param values: the annotated names of the inherited values to answer
    :param scope: queryset of the ids of the layers the effective values are
        computed for. The effective value of a layer only depends on its own
        ancestry, which is looked up in all layers of the registry, so the scope
        decides for how many layers the values are answered and never which
        value a layer gets (#1315). Without a scope the values of every layer of
        the registry are computed.
    """

    def __init__(self,
                 values=[
                     "is_queryable_inherited",
                     "is_cascaded_inherited",
                     "is_opaque_inherited",
                     "scale_min_inherited",
                     "scale_max_inherited",
                     "bbox_lat_lon_inherited"
                 ],
                 scope=None,
                 *args,
                 **kwargs):

        from registry.models.service import Layer
        layers = Layer.objects if scope is None else Layer.objects.filter(
            pk__in=scope)
        super(AncestorsHeritageCTE, self).__init__(
            queryset=layers.with_inherited_values().values(
                "id",
                *values
            ),
            name="ancestors",
            *args,
            **kwargs
        )


class AncestorsHeritageAggregatedCTE(CTE):
    """The aggregated attributes of layers, answered per layer.

    :param values: the annotated names of the aggregated values to answer
    :param scope: queryset of the ids of the layers the values are aggregated
        for; the aggregation groups by layer, so the scope only decides how many
        layers are aggregated (#1315).
    """

    def __init__(self,
                 values=[
                     "reference_systems_inherited",
                     "time_extents_inherited",
                     "styles_inherited",
                 ],
                 scope=None,
                 *args,
                 **kwargs):
        from registry.models.service import Layer
        layers = Layer.objects if scope is None else Layer.objects.filter(
            pk__in=scope)
        super(AncestorsHeritageAggregatedCTE, self).__init__(
            queryset=layers.with_aggregated_inherited_values().values(
                "id",
                *values
            ),
            name="aggregated_ancestors",
            *args,
            **kwargs
        )
