from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters import BooleanFilter, ChoiceFilter, NumberFilter
from django_filters.filterset import FilterSet
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.querys.historical import with_delta_size


class HistoricalFilterSet(FilterSet):
    delta = ChoiceFilter(
        choices=(("None", "None"),),
        method="filter_delta",
        help_text=_("Returns records without a previous historical record."),
    )
    delta_size__gt = NumberFilter(
        method="filter_delta_size_gt",
        min_value=0,
        help_text=_(
            "Returns records with more than this many changed fields."),
    )

    changed_or_created = BooleanFilter(
        method="filter_changed_or_created",
        help_text=_(
            "Returns creation records or records with changed fields. "
            "False leaves the queryset unchanged."),
    )

    changed_or_deleted = BooleanFilter(
        method="filter_changed_or_deleted",
        help_text=_(
            "Returns deleted records or records with changed fields. "
            "False leaves the queryset unchanged."),
    )

    class Meta:
        fields = {
            "id": ["exact", "in"],
            "history_relation": ["exact"],
            "history_change_reason": [
                "exact", "iexact", "icontains", "contains", "in",
            ],
            "history_date": ["exact", "gte", "lte", "range"],
        }

    def filter_delta(self, queryset, name, value):
        return queryset.filter(prev_record_id__isnull=True)

    def filter_delta_size_gt(self, queryset, name, value):
        return with_delta_size(queryset).filter(_delta_size__gt=value)

    def filter_changed_or_created(self, queryset, name, value):
        if not value:
            return queryset
        return with_delta_size(queryset).filter(
            Q(_delta_size__gt=0) | Q(history_type="+")
        )

    def filter_changed_or_deleted(self, queryset, name, value):
        if not value:
            return queryset
        return with_delta_size(queryset).filter(
            Q(_delta_size__gt=0) | Q(history_type="-")
        )


class WebMapServiceHistoricalFilterSet(HistoricalFilterSet):
    class Meta(HistoricalFilterSet.Meta):
        model = WebMapService.change_log.model


class LayerHistoricalFilterSet(HistoricalFilterSet):
    change_type = ChoiceFilter(
        choices=(("modified", _("Changed")), ("unchanged", _("Unchanged")),
                 ("removed", _("Deleted")), ("added", _("Added"))),
        method="filter_change_type",
        help_text=_("Filter layer history by the kind of recorded change."),
    )

    def filter_change_type(self, queryset, name, value):
        if value == "removed":
            return queryset.filter(history_type="-")
        added = Q(history_type="+") | Q(prev_record_id__isnull=True)
        if value == "added":
            return queryset.exclude(history_type="-").filter(added)
        queryset = with_delta_size(queryset.filter(history_type="~").exclude(added))
        return queryset.filter(**{
            "_delta_size__gt" if value == "modified" else "_delta_size": 0,
        })

    class Meta(HistoricalFilterSet.Meta):
        model = Layer.change_log.model
        fields = {
            **HistoricalFilterSet.Meta.fields,
            "service": ["exact"],
        }


class WebFeatureServiceHistoricalFilterSet(HistoricalFilterSet):
    class Meta(HistoricalFilterSet.Meta):
        model = WebFeatureService.change_log.model


class FeatureTypeHistoricalFilterSet(HistoricalFilterSet):
    class Meta(HistoricalFilterSet.Meta):
        model = FeatureType.change_log.model
        fields = {
            **HistoricalFilterSet.Meta.fields,
            "service": ["exact"],
        }


class CatalogueServiceHistoricalFilterSet(HistoricalFilterSet):
    class Meta(HistoricalFilterSet.Meta):
        model = CatalogueService.change_log.model
