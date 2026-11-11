"""The sort of a list by the next run of its schedules.

The next run of a scheduled setting is no column: a crontab occurrence is
decided in python (:func:`extras.scheduling.next_run_expected_at`), so a list
which offers ``sort=nextRunAt`` cannot let the plain ordering filter ask the
database for a column it does not have. This backend decides the moments of
the rows while the queryset still belongs to the whole list - :func:`extras.
scheduling.with_next_run_at` answers them back as one annotation - and hands
the annotated queryset to the ordinary ordering, so the page, the filters and
the count of the request stay in the database (#1082).
"""
from extras.scheduling import with_next_run_at
from rest_framework_json_api.filters import OrderingFilter
from rest_framework_json_api.utils import undo_format_field_name


class NextRunOrderingFilter(OrderingFilter):
    """The ordering filter of a list whose rows answer a next run.

    A request sorts by the next run by naming ``nextRunAt`` (or the spelling
    of the database) in its ``sort`` parameter; only such a request pays for
    the python decision of the moments.
    """

    #: the annotation which answers the next run, and the sort term naming it
    next_run_field = "next_run_at"

    def filter_queryset(self, request, queryset, view):
        sort = request.query_params.get(self.ordering_param, "")
        # the same normalisation the ordering itself applies to the terms
        terms = {
            undo_format_field_name(term.replace(".", "__").lstrip("-"))
            for term in sort.split(",") if term.strip()}
        if self.next_run_field in terms:
            queryset = with_next_run_at(queryset)
        return super().filter_queryset(request, queryset, view)
