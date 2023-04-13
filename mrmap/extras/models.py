
from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models.expressions import Value
from django.db.models.functions import JSONObject
from django.db.models.query import Q


class HistoricalRecordMixin:

    def save(self, without_historical: bool = False, *args, **kwargs):
        if without_historical:
            self.skip_history_when_saving = True
        try:
            ret = super().save(*args, **kwargs)
        finally:
            if without_historical:
                del self.skip_history_when_saving
        return ret


JSONObject(
    pk="pk",
    lft="lft",
    rgt="rgt",
    depth="depth",
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
