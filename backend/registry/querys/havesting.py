"""The queryset of the harvesting jobs.

Filed next to the manager of the aggregate (`registry/managers/havesting.py`), whose
methods return querysets of these classes.
"""

from django_cte import CTEQuerySet


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
