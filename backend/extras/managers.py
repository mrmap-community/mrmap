from collections.abc import Mapping
from typing import Any

from django.db import models
from django.db.models import (Case, CharField, Count, F, Q, Value, When)
from django.db.models.constraints import UniqueConstraint
from django.db.models.query import Prefetch
from registry.querys.historical import with_delta_size


class UniqueConstraintDefaultValueManager(models.Manager):
    """ Custom manager which provides a custom get_or_create

    Iterates over the model meta constraint list, filtered by the type 'UniqueConstraint'
    to correctly use get_or_create
    """

    def get_or_create(self, defaults: Mapping[str, Any] | None = None, **kwargs: Any) -> tuple[models.Model, bool]:
        for constraint in list(filter(lambda constraint: isinstance(constraint, UniqueConstraint), self.model._meta.constraints)):
            for field in constraint.fields:
                kwargs.update({
                    field: kwargs.get(field, self.model._meta.get_field(field).get_default()),
                })
        return super().get_or_create(defaults=defaults, **kwargs)


class DefaultHistoryManager(models.Manager):

    def with_history(self):
        """Return the last two historical records to diff them"""
        return self.get_queryset()\
            .prefetch_related(
                Prefetch(
                    'change_log',
                    queryset=self.model.change_log.all(),
                    to_attr='prefetched_history'
                )
        )

    def filter_first_history(self):
        return self.model.change_log.filter(history_type='+').select_related('history_user').only('history_relation', 'history_user__id', 'history_date')

    def filter_last_history(self):
        return self.model.change_log.filter(history_date=self.model.change_log.values_list('history_date', flat=True)[:1]).select_related('history_user').only('history_relation', 'history_user__id', 'history_date').order_by('history_date')

    def filter_delete_history(self):
        return self.model.change_log.filter(history_date=self.model.change_log.values_list('history_date', flat=True)[:1], history_type='-').select_related('history_user').only('history_relation', 'history_user__id', 'history_date').order_by('history_date')

    def _stats_per_day_queryset(self, group_by_service: bool = False):
        history_model = self.model.change_log.model

        # How many tracked fields an audit row differs in from the row it
        # precedes is something the row knows about itself: the database wrote
        # it when the row was written (registry migration 0025), which is what
        # leaves this aggregation with a single pass over the table. Without a
        # predecessor a row has no diff size at all, which is how a record which
        # was created before history existed is told apart from a save which
        # changed nothing -- the first counts as new, the second as nothing.
        history = with_delta_size(history_model._default_manager.all())

        new_filter = (
            Q(history_type="+")
            | Q(
                history_type="~",
                _delta_size__isnull=True,
            )
        )

        updated_filter = Q(
            history_type="~",
            _delta_size__gt=0,
        )

        deleted_filter = Q(history_type="-")

        # Remove unchanged "~" entries, but always retain + and -.
        history = history.filter(
            Q(history_type="+")
            | Q(history_type="-")
            | updated_filter
            | Q(
                history_type="~",
                _delta_size__isnull=True,
            )
        )

        group_fields = ["history_day"]

        if group_by_service:
            group_fields.append("service")

        return (
            history
            .values(*group_fields)
            .annotate(
                id=F("history_day"),
                new=Count(
                    "history_id",
                    filter=new_filter,
                ),
                deleted=Count(
                    "history_id",
                    filter=deleted_filter,
                ),
                updated=Count(
                    "history_id",
                    filter=updated_filter,
                ),
            )
            .order_by(*group_fields)
        )

    def new_per_day(self):
        return self.filter_first_history().values("history_day").annotate(
            id=F("history_day"),
            new=Count("pk")
        ).order_by("id")

    def deleted_per_day(self):
        return self.filter_delete_history().values("history_day").annotate(
            id=F("history_day"),
            deleted=Count("pk")
        ).order_by("id")

    def stats_per_day(self):
        return self._stats_per_day_queryset()

    def stats_per_day_per_service(self):
        return self._stats_per_day_queryset(group_by_service=True)


class ChoiceManager(models.Manager):
    def with_label(self):
        cases = [
            When(value=value, then=Value(str(label)))
            for value, label in self.model.CHOICES
        ]
        return self.get_queryset().annotate(
            label=Case(*cases, output_field=CharField())
        )
