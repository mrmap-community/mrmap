from django.db import connection
from django.db.models.fields import DateField, IntegerField, UUIDField
from django.db.models.indexes import Index
from django.db.models.query import QuerySet
from django_pgviews import view as pg
from registry.models.harvest import HarvestedMetadataRelation
from registry.models.metadata import (DatasetMetadataRecord,
                                      ServiceMetadataRecord)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)


def queryset_view_sql(queryset) -> pg.ViewSQL:
    """The statement a queryset answers, with its parameters set inline.

    A view is created by one statement which takes no parameters, so the
    queryset is answered once with the debug cursor on and the statement it
    leaves behind is the one the view is created from.

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


class DynamicMaterializedView(pg.MaterializedView):
    base_model = None

    class Meta:
        managed = False
        abstract = True

    @classmethod
    def get_queryset(cls) -> QuerySet:
        return cls.base_model.objects.get_queryset()

    @classmethod
    def get_sql(cls):
        return queryset_view_sql(cls.get_queryset().all())


class ResourceHistroyStatsPerDay(DynamicMaterializedView):
    id = DateField(primary_key=True)
    history_day = DateField()
    new = IntegerField()
    updated = IntegerField()
    deleted = IntegerField()

    class Meta:
        managed = False
        abstract = True
        indexes = [
            Index(fields=["id"]),
            Index(fields=["history_day"]),
            Index(fields=["new"]),
            Index(fields=["updated"]),
            Index(fields=["deleted"]),
        ]

    @classmethod
    def get_queryset(cls):
        return cls.base_model.history.stats_per_day()


class ResourceHistoryStatsPerDayAndService(DynamicMaterializedView):
    id = DateField(primary_key=True)
    history_day = DateField()
    new = IntegerField()
    updated = IntegerField()
    deleted = IntegerField()
    service = UUIDField()

    class Meta:
        managed = False
        abstract = True
        indexes = [
            Index(fields=["id"]),
            Index(fields=["history_day"]),
            Index(fields=["new"]),
            Index(fields=["updated"]),
            Index(fields=["deleted"]),
            Index(fields=["service"]),
        ]

    @classmethod
    def get_queryset(cls):
        return cls.base_model.history.stats_per_day_per_service()


class MaterializedDatasetMetadataRecordStatsPerDay(ResourceHistroyStatsPerDay):
    base_model = DatasetMetadataRecord

    class Meta:
        managed = False
        indexes = ResourceHistroyStatsPerDay.Meta.indexes


class MaterializedServiceMetadataRecordStatsPerDay(ResourceHistroyStatsPerDay):
    base_model = ServiceMetadataRecord

    class Meta:
        managed = False
        indexes = ResourceHistroyStatsPerDay.Meta.indexes


class MaterializedWebMapServiceStatsPerDay(ResourceHistroyStatsPerDay):
    base_model = WebMapService

    class Meta:
        managed = False
        indexes = ResourceHistroyStatsPerDay.Meta.indexes


class MaterializedLayerStatsPerDay(ResourceHistroyStatsPerDay):
    base_model = Layer

    class Meta:
        managed = False
        indexes = ResourceHistroyStatsPerDay.Meta.indexes


class MaterializedLayerStatsPerDayAndService(ResourceHistoryStatsPerDayAndService):
    base_model = Layer

    class Meta:
        managed = False
        indexes = ResourceHistoryStatsPerDayAndService.Meta.indexes


class MaterializedWebFeatureServiceStatsPerDay(ResourceHistroyStatsPerDay):
    base_model = WebFeatureService

    class Meta:
        managed = False
        indexes = ResourceHistroyStatsPerDay.Meta.indexes


class MaterializedFeatureTypeStatsPerDay(ResourceHistroyStatsPerDay):
    base_model = FeatureType

    class Meta:
        managed = False
        indexes = ResourceHistroyStatsPerDay.Meta.indexes


class MaterializedCatalogueServiceStatsPerDay(ResourceHistroyStatsPerDay):
    base_model = CatalogueService

    class Meta:
        managed = False
        indexes = ResourceHistroyStatsPerDay.Meta.indexes


class MaterializedHarvestingStatsPerDay(DynamicMaterializedView):
    id = DateField(primary_key=True)
    history_day = DateField()
    service = UUIDField()
    harvesting_job = IntegerField()
    new = IntegerField()
    updated = IntegerField()
    existed = IntegerField()

    base_model = HarvestedMetadataRelation

    class Meta:
        managed = False
        indexes = [
            Index(fields=["id"]),
            Index(fields=["history_day"]),
            Index(fields=["service"]),
            Index(fields=["harvesting_job"]),
            Index(fields=["new"]),
            Index(fields=["updated"]),
            Index(fields=["existed"]),
        ]

    @classmethod
    def get_queryset(cls):
        return cls.base_model.objects.stats_per_day()
