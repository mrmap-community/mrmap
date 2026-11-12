"""The rows of the attention which the services of a deployment answer.

The states which need the attention of an administrator are decided in
`registry/querys/alerts.py`: they are annotated to the services themselves and
projected into the one relation of alert rows which this table answers. The
rows are no second definition of the rules - `refresh_service_alerts()` writes
exactly the rows which the union of those annotations projects - but it writes
them once per change and per beat fire instead of on every read, so that the
header poll of the alert list is an indexed read of a bounded relation and not
a re-evaluation of the whole derivation (#1030).

Nothing which the refresh writes is decided twice: it reads the services,
their runs and jobs as they are, and the row of an alert exists only while the
state behind it does. The schedules which did not keep their time are written
by the same refresh, because a crontab is calculated in python - see
`registry/querys/alerts.py` and `extras/scheduling.py`.
"""
from django.db import models


class ServiceAlert(models.Model):
    """One problem of one service, of every kind of service, in one row.

    The identity of a row is the identity of the problem behind it, so an
    alert which stays open keeps its identifier across refreshes and a problem
    which is fixed leaves no row behind. The indexes answer the two reads the
    api of the alerts makes: the scoped page of the attention, ordered by
    severity and date, and the rows of one service which a refresh replaces.
    """

    id = models.CharField(primary_key=True)
    severity = models.CharField()
    category = models.CharField()
    message = models.CharField()
    service_type = models.CharField()
    service = models.CharField()
    service_title = models.CharField()
    resource_type = models.CharField()
    resource_id = models.CharField()
    occurred_at = models.DateTimeField(null=True)
    target_path = models.CharField()

    class Meta:
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['service']),
            models.Index(fields=['service_type', 'service']),
        ]
