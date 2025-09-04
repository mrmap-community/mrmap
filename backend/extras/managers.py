from typing import Any, MutableMapping, Optional, Tuple, TypeVar

from django.db import models
from django.db.models import Case, Count, F, Q, Value, When
from django.db.models.constraints import UniqueConstraint
from django.db.models.query import Prefetch

T = TypeVar('T')


class UniqueConstraintDefaultValueManager(models.Manager):
    """ Custom manager which provides a custom get_or_create

    Iterates over the model meta constraint list, filtered by the type 'UniqueConstraint'
    to correctly use get_or_create
    """

    def get_or_create(self, defaults: Optional[MutableMapping[str, Any]] = None, **kwargs: Any) -> Tuple[T, bool]:
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
        created_filter = Q(history_type='+')
        final_deleted_filter = Q(history_date=self.model.change_log.values_list(
            'history_date', flat=True)[:1], history_type='-')
        final_updated_filter = Q(history_date=self.model.change_log.values_list(
            'history_date', flat=True)[:1], history_type='~')
        created_or_final_delete = self.model.change_log.filter(
            created_filter | final_deleted_filter | final_updated_filter
        )
        return created_or_final_delete.annotate(
            created=Case(When(condition=created_filter,
                         then=Value(True)), default=Value(False)),
            final_deleted=Case(When(condition=final_deleted_filter,
                                    then=Value(True)), default=Value(False)),
            final_updated=Case(When(condition=final_updated_filter,
                                    then=Value(True)), default=Value(False)),
        ).values("history_day").annotate(
            id=F("history_day"),
            new=Count("pk", filter=Q(created=True)),
            deleted=Count("pk", filter=Q(final_deleted=True)),
            updated=Count("pk", filter=Q(final_updated=True))
        )
