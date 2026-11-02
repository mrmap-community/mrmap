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
from django.db import connection
from django.db.models import CharField, DateTimeField
from django_pgviews import view as pg


def queryset_view_sql(queryset) -> pg.ViewSQL:
    """The statement a queryset answers, with its parameters set inline.

    A view is created by one statement which takes no parameters, so the
    queryset is answered once with the debug cursor on and the statement it
    leaves behind is the one the view is created from.

    This is next to the only view of the project on purpose: the statistics
    views which used it too were dropped when their endpoints started answering
    their aggregation themselves (#857), so there is nothing left to share this
    with.

    Args:
        queryset: the queryset which answers the rows of the view

    Returns:
        ViewSQL: the statement the view is created by
    """
    # sql debug cursor is only available on debug True. So we need to force it temporaly
    # https://docs.djangoproject.com/en/5.0/faq/models/#how-can-i-see-the-raw-sql-queries-django-is-running
    connection.force_debug_cursor = True
    # repr() --> this will trigger the execition
    list(queryset)
    # get the last query; this should be the execution from the line below
    last_query = connection.queries[-1].get('sql')
    connection.force_debug_cursor = False
    return pg.ViewSQL(last_query, None)


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
