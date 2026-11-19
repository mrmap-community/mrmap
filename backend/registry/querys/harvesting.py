"""The queryset of the harvesting jobs.

Filed next to the manager of the aggregate (`registry/managers/harvesting.py`), whose
methods return querysets of these classes.
"""

from django.db.models import DateTimeField, F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django_cte import CTEQuerySet


def run_created_at():
    """The moment a run was made, as the database answers it for every row.

    `date_created` answers the creation of a run made since #1079, which gave the
    field the default its own comment asks for and filled the runs a deployment
    already has from their change log. What stays is the row whose creation cannot
    be known - `null=True` is kept for exactly that - and for it the moment is read
    from the first row of the change log, the same source which answers who made a
    run. Every question about the time a run took has to keep that fallback, or the
    runs of a deployment which has harvested for years answer nothing (#693, #1071).
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

    def for_client_access(self):
        """Read plan of a task which asks the catalogue's client (#1392).

        The download half of a harvest builds the OGC client of the job's
        service: the service row, and behind it the auth records a session
        is built from. Without the join every such fire paid its lazy
        SELECTs one by one on top of its locked job read - the audit row
        ``call_fetch_total_records`` of ``celery-task-orm-audit``. The task
        of the download phase reads job, service and auth as one statement
        over this plan; the sibling ``call_fetch_records`` already did it
        inline and reads through here since.

        Cardinality: 1 row per job, two one-to-one joins. The job's backlog
        is not part of any plan of this family - it is the table the import
        drains row by row (#1397's do-not-prefetch-the-backlog rule).

        The row lock a task takes stays an explicit call-site operation
        (``select_for_update(of=("self",))`` - ``of`` because the join must
        not widen the lock to the catalogue's rows, rule 3 of the manager
        conventions), not part of this plan.
        """
        return self.select_related("service", "service__auth")
