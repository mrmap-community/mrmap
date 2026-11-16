"""Page-bounded schedule warnings for the settings endpoints.

The serializers of the scheduled settings answer `scheduleWarnings` from a
batch which their viewset reads for the whole page at once - the same data
flow which the alerts of a services page use (`registry.querys.alerts.
alert_records` and its viewset). What a list pays per request this way is one
aggregate of duration evidence and the crontab decision of the rows shown; a
detail read answers its single row in the serializer itself (#1332).
"""
from registry.querys.schedule_warnings import schedule_warnings_by_id


class ScheduleWarningsViewsetMixin:
    """Reads the schedule warnings of a page before its rows are serialized.

    Mix into the viewset of a scheduled setting. Endpoints which know sparse
    fieldsets are asked first: a screen which shows no warning column pays for
    no evidence query, exactly like the next-run answers of the schedules
    (#1082).
    """

    def paginate_queryset(self, queryset, *args, **kwargs):
        """Decide the warnings of the page once, not once per row."""
        page = super().paginate_queryset(queryset, *args, **kwargs)
        if page:
            check = getattr(self, "check_sparse_fields_contains", None)
            if check is None or check("scheduleWarnings"):
                self.schedule_warnings = schedule_warnings_by_id(page)
        return page

    def get_serializer_context(self):
        """Hand the warnings read for the page to the serializers."""
        context = super().get_serializer_context()
        context["schedule_warnings"] = getattr(self, "schedule_warnings", None)
        return context
