from django.contrib.gis.db.models import MultiPolygonField
from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import \
    GinIndex  # add the Postgres recommended GIN index
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import connection, models, transaction
from django.db.models import Q
from django.db.models.expressions import F, Func, Value
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django_pgviews import view as pg
from registry.models.metadata import (AbstractMetadata, DatasetMetadataRecord,
                                      ServiceMetadataRecord)


class SearchableMetadataRecordAbstract(AbstractMetadata, pg.MaterializedView):

    title: str = models.CharField(max_length=1000,
                                  default="")
    abstract = models.TextField(default="")
    file_identifier = models.CharField(max_length=1000)
    code = models.CharField(max_length=4096,
                            default="")
    code_space = models.CharField(max_length=4096,
                                  default="")
    resource_identifier = models.CharField(max_length=4096,
                                           default="")

    keywords_list = ArrayField(
        base_field=models.CharField(max_length=300),
        default=list,
        editable=False,
    )
    bounding_geometry = MultiPolygonField(null=True,
                                          blank=True, )

    search_vector = SearchVectorField()

    base_model = None

    @classmethod
    def get_queryset(cls):
        return cls.base_model.objects.annotate(
            keyword_list=ArrayAgg(
                "keywords__keyword",
                distinct=True,
                # non empty lexeme inside keywords_list
                filter=~Q(keywords__keyword=""),
                default=[]

            )
        ).annotate(
            search_vector=SearchVector(
                F("title"),
                F("abstract"),
                F("file_identifier"),
                F("code"),
                F("code_space"),
                Func(
                    "keyword_list",
                    function="array_to_tsvector",
                    output_field=SearchVectorField()
                ),
                config="english"  # config="english" is just a dummy; to get imutable searchvector results
            )
        )

    @classmethod
    def get_sql(cls):
        # sql debug cursor is only available on debug True. So we need to force it temporaly
        # https://docs.djangoproject.com/en/5.0/faq/models/#how-can-i-see-the-raw-sql-queries-django-is-running
        connection.force_debug_cursor = True
        # repr() --> this will trigger the execition
        list(cls.get_queryset().all())
        # get the last query; this should be the execution from the line below
        last_query = connection.queries[-1].get('sql')
        connection.force_debug_cursor = False
        return pg.ViewSQL(last_query, None)

    class Meta:
        abstract = True
        managed = False
        indexes = [
            models.Index(fields=["title",]),
            models.Index(fields=["abstract",]),
            models.Index(fields=["file_identifier"]),
            models.Index(fields=["resource_identifier"]),
            GinIndex(fields=["search_vector"]),
        ]


class SearchableDatasetMetadataRecord(SearchableMetadataRecordAbstract):
    base_model = DatasetMetadataRecord

    @classmethod
    def get_queryset(cls):
        return super().get_queryset().annotate(
            hierarchy_level=Value("dataset")
        )

    class Meta:
        managed = False
        indexes = SearchableMetadataRecordAbstract._meta.indexes


@receiver(m2m_changed, sender=DatasetMetadataRecord.keywords.through)
@receiver([post_save, post_delete], sender=DatasetMetadataRecord)
def update_dataset_view(*args, **kwargs):
    transaction.on_commit(lambda: SearchableDatasetMetadataRecord.refresh())


class SearchableServiceMetadataRecord(SearchableMetadataRecordAbstract):
    base_model = ServiceMetadataRecord

    @classmethod
    def get_queryset(cls):
        return super().get_queryset().annotate(
            hierarchy_level=Value("service")
        )

    class Meta:
        managed = False
        indexes = SearchableMetadataRecordAbstract._meta.indexes


@receiver(m2m_changed, sender=ServiceMetadataRecord.keywords.through)
@receiver([post_save, post_delete], sender=ServiceMetadataRecord)
def update_service_view(*args, **kwargs):
    transaction.on_commit(lambda: SearchableServiceMetadataRecord.refresh())
