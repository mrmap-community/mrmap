"""The alerts of every service of a deployment as one relation.

The states which need the attention of an administrator are decided in
`registry/querys/alerts.py` and are answered to the services themselves as
annotations. This view projects the same annotations into one relation of
alert rows, so that the cross-service overview of the attention is answered
by one query of the database instead of one query per kind of service.

Nothing which this view answers is stored: it reads the services, their runs
and jobs as they are, and the row of an alert exists only while the state
behind it does. The schedules which did not keep their time are not answered
here, because a crontab is calculated in python - see
`registry/querys/alerts.py` and `extras/scheduling.py`.
"""
from django.db.models import CharField, DateTimeField
from django_pgviews import view as pg
from registry.models.materialized_views import queryset_view_sql


class ServiceAlertView(pg.ReadOnlyView):
    """One problem of one service, of every kind of service, in one row.

    The sql of this view is not written down but answered by the union which
    `registry/querys/alerts.py` builds from the alert annotations - the same
    rules as the services themselves answer, so that the overview of the
    attention and the services cannot drift apart.
    """

    id = CharField(primary_key=True, db_column='alert_id')
    severity = CharField(db_column='alert_severity')
    category = CharField(db_column='alert_category')
    message = CharField(db_column='alert_message')
    service_type = CharField(db_column='alert_service_type')
    service = CharField(db_column='alert_service')
    service_title = CharField(db_column='alert_service_title')
    resource_type = CharField(db_column='alert_resource_type')
    resource_id = CharField(db_column='alert_resource_id')
    occurred_at = DateTimeField(null=True, db_column='alert_occurred_at')
    target_path = CharField(db_column='alert_target_path')

    class Meta:
        managed = False

    @classmethod
    def get_queryset(cls):
        from registry.querys.alerts import service_alert_rows
        return service_alert_rows()

    @classmethod
    def get_sql(cls):
        return queryset_view_sql(cls.get_queryset())
