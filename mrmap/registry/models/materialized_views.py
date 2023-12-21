

from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import \
    GinIndex  # add the Postgres recommended GIN index
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import connection, models
from django.db.models import Q
from django.db.models.expressions import F, Func
from django.db.models.signals import (m2m_changed, post_delete, post_save,
                                      receiver)
from django_pgviews import view as pg
from registry.models.metadata import DatasetMetadataRecord


class SearchableDatasetMetadataRecord(pg.MaterializedView):

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

    search_vector = SearchVectorField()

    @classmethod
    def get_sql(cls):
        repr(
            DatasetMetadataRecord.objects.annotate(
                keyword_list=ArrayAgg(
                    "keywords__keyword",
                    distinct=True,
                    # non empty lexeme inside keywords_list
                    filter=~Q(keywords__keyword=""),
                    default=[]

                )
            )
            .annotate(
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
        )  # repr() --> this will trigger the execition
        # get the last query; this should be the execution from the line below
        last_query = connection.queries[-1].get('sql')
        return pg.ViewSQL(last_query, None)

    class Meta:
        managed = False
        indexes = [
            models.Index(fields=["title",]),
            models.Index(fields=["abstract",]),
            models.Index(fields=["file_identifier"]),
            models.Index(fields=["resource_identifier"]),
            GinIndex(fields=["search_vector"]),
        ]


@receiver(m2m_changed, sender=DatasetMetadataRecord.keywords.through)
@receiver([post_save, post_delete], sender=DatasetMetadataRecord)
def update_view(*args, **kwargs):
    SearchableDatasetMetadataRecord.refresh()
    # TODO: refresh on bulk operations
