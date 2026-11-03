from django_filters import FilterSet, NumberFilter, UUIDFilter
from registry.models.harvest import HarvestedMetadataRelation
from registry.models.service import FeatureType, Layer


class StatisticalFeatureTypePerServiceFilterSet(FilterSet):
    service = UUIDFilter()

    class Meta:
        model = FeatureType.change_log.model
        fields = ('service',)


class StatisticalLayerPerServiceFilterSet(FilterSet):
    service = UUIDFilter()

    class Meta:
        model = Layer.change_log.model
        fields = ('service',)


class StatisticalHarvestedMetadataRelationFilterSet(FilterSet):
    """The days a harvesting job wrote relations, for one service or one job.

    Both filters name the aggregation of `HarvestedMetadataRelation` which the
    endpoint answers, not a field of the relation itself: the service of a
    harvested relation is the service of its job, and the day, the counters and
    the job are what the aggregation groups by.

    Both are declared instead of being left to the model, because the auto
    generated filter of a foreign key is a `ModelChoiceFilter`, which refuses an
    id it does not know with `invalid_choice` where the aggregation answers no
    rows -- which is also what these filters answered before, while the
    statistics were read from a view that carried both as plain columns.
    """

    service = UUIDFilter(field_name="harvesting_job__service")
    harvesting_job = NumberFilter(field_name="harvesting_job")

    class Meta:
        model = HarvestedMetadataRelation
        fields = ()
