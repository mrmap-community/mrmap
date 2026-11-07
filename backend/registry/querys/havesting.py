"""The queryset of the harvesting jobs.

Filed next to the manager of the aggregate (`registry/managers/havesting.py`), whose
methods return querysets of these classes.
"""

from django.db.models import DateTimeField, F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django_cte import CTEQuerySet


def run_created_at():
    """The moment a run was made, as the database answers it for every row.

    `date_created` is nullable and only set explicitly (see `ProcessingData`), and
    the harvesting never sets it, so the creation of a run is read from the first
    row of its change log - the same source which answers who made a run. Every
    question about the time a run took has to fall back to it, or the runs of a
    deployment which has harvested for years answer nothing (#693, #1071).
    """
    from registry.models.harvest import HarvestingJob

    return Coalesce(
        F('date_created'),
        Subquery(
            HarvestingJob.change_log.model.objects
            .filter(history_relation_id=OuterRef('pk'))
            .order_by('history_date', 'history_id')
            .values('history_date')[:1],
            output_field=DateTimeField()))


class HarvestingJobQuerySet(CTEQuerySet):
    """A queryset of the harvesting jobs which can be counted without the database.

    The list of the harvesting jobs answers the statistics of every job from the
    ``sums`` CTE, which aggregates the whole table of the harvested metadata
    relations, and the paginator of the endpoint asks that very queryset for the
    number of rows of the answer: the aggregation of the whole table cost two
    materializations per request, where the second one answered a number which the
    rows of the job table answer as well (#885).
    """

    def with_cached_count(self, count):
        """Carry ``count`` as the number of rows, which ``count()`` answers with.

        The number belongs to a request and not to a queryset - a queryset which
        answers two requests would tell the second one the number of the first - so
        the view which read it hands it over here and nothing else does (#885).
        """
        qs = self._clone()
        qs._cached_count = count
        return qs

    def count(self):
        if getattr(self, '_cached_count', None) is not None:
            return self._cached_count
        return super().count()
