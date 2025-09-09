from django.contrib.postgres.aggregates.general import BoolOr
from django.db.models.expressions import F, Value
from django.db.models.query_utils import Q
from django_cte import CTE


class LayerSecurityInformationCTE(CTE):
    def __init__(self, *args, **kwargs):
        from registry.models.security import AllowedWebMapServiceOperation
        super(LayerSecurityInformationCTE, self).__init__(
            queryset=AllowedWebMapServiceOperation.objects.annotate(
                layer_id=F("secured_layers__id")
            )
            .values("layer_id")
            .annotate(
                is_secured=BoolOr(Value(True)),
                is_spatial_secured=BoolOr(Q(allowed_area__isnull=False)),
            )
            .values("layer_id", "is_secured", "is_spatial_secured"),
            name="layer_security_information",
            *args,
            **kwargs
        )


class AncestorsHeritageCTE(CTE):
    def __init__(self, *args, **kwargs):
        from registry.models.service import Layer
        super(AncestorsHeritageCTE, self).__init__(
            queryset=Layer.objects.with_inherited_values().values(
                "id",
                "is_queryable_inherited",
                "is_cascaded_inherited",
                "is_opaque_inherited",
                "scale_min_inherited",
                "scale_max_inherited",
                "bbox_lat_lon_inherited",
            ),
            name="ancestors",
            *args,
            **kwargs
        )


class AncestorsHeritageAggregatedCTE(CTE):
    def __init__(self, *args, **kwargs):
        from registry.models.service import Layer
        super(AncestorsHeritageAggregatedCTE, self).__init__(
            queryset=Layer.objects.with_aggregated_inherited_values().values(
                "id",
                "reference_systems_inherited",
                "dimensions_inherited",
                "styles_inherited",
            ),
            name="aggregated_ancestors",
            *args,
            **kwargs
        )
