"""The changes of every resource of the registry, counted per day.

Every endpoint of this module answers its rows straight from the records the
changes are written to: a per-day statistics row is one aggregation over the
audit records of a resource, whose day is a persisted column of those records
(#856), so the answer is the same whether it is asked a second after the change
or a day later. It used to be answered from a materialized view which a
periodic task rebuilt eleven times an hour -- which a change therefore had to
wait for, and which every harvest made the database rebuild over and over.
"""
from registry.filters.statistical import (
    StatisticalFeatureTypePerServiceFilterSet,
    StatisticalHarvestedMetadataRelationFilterSet,
    StatisticalLayerPerServiceFilterSet)
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import (DatasetMetadataRecord,
                                      ServiceMetadataRecord)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.serializers.statistical import (
    StatisticalCatalogueServiceSerializer,
    StatisticalDatasetMetadataRecordSerializer,
    StatisticalFeatureTypePerServiceSerializer, StatisticalFeatureTypeSerializer,
    StatisticalHarvestedMetadataRelationSerializer,
    StatisticalLayerPerServiceSerializer, StatisticalLayerSerializer,
    StatisticalServiceMetadataRecordSerializer,
    StatisticalWebFeatureServiceSerializer, StatisticalWebMapServiceSerializer)
from rest_framework.response import Response
from rest_framework_json_api.views import generics


class StatisticalListView(generics.ListAPIView):
    """The days a resource changed, as the aggregation over its audit records.

    ``id`` is the day of the changes -- the aggregation answers it as the day
    itself, which is what the frontend charts order and label their axis by.
    """
    ordering_fields = ["id"]


class StatisticalDatasetMetadataRecordListView(StatisticalListView):
    queryset = DatasetMetadataRecord.history.stats_per_day()
    serializer_class = StatisticalDatasetMetadataRecordSerializer


class StatisticalServiceMetadataRecordListView(StatisticalListView):
    queryset = ServiceMetadataRecord.history.stats_per_day()
    serializer_class = StatisticalServiceMetadataRecordSerializer


class StatisticalWebMapServiceListView(StatisticalListView):
    queryset = WebMapService.history.stats_per_day()
    serializer_class = StatisticalWebMapServiceSerializer


class StatisticalLayerListView(StatisticalListView):
    queryset = Layer.history.stats_per_day()
    serializer_class = StatisticalLayerSerializer


class StatisticalLayerPerServiceListView(StatisticalListView):
    queryset = Layer.history.stats_per_day_per_service()
    serializer_class = StatisticalLayerPerServiceSerializer
    filterset_class = StatisticalLayerPerServiceFilterSet


class StatisticalWebFeatureServiceListView(StatisticalListView):
    queryset = WebFeatureService.history.stats_per_day()
    serializer_class = StatisticalWebFeatureServiceSerializer


class StatisticalFeatureTypeListView(StatisticalListView):
    queryset = FeatureType.history.stats_per_day()
    serializer_class = StatisticalFeatureTypeSerializer


class StatisticalFeatureTypePerServiceListView(StatisticalListView):
    queryset = FeatureType.history.stats_per_day_per_service()
    serializer_class = StatisticalFeatureTypePerServiceSerializer
    filterset_class = StatisticalFeatureTypePerServiceFilterSet


class StatisticalCatalogueServiceListView(StatisticalListView):
    queryset = CatalogueService.history.stats_per_day()
    serializer_class = StatisticalCatalogueServiceSerializer


class StatisticalHarvestedMetadataRelationListView(StatisticalListView):
    # what a harvesting job found on a day is not an audit record but the
    # relation it wrote, so this one answers the relation table itself
    filterset_class = StatisticalHarvestedMetadataRelationFilterSet
    queryset = HarvestedMetadataRelation.objects.stats_per_day()
    serializer_class = StatisticalHarvestedMetadataRelationSerializer

    def list(self, request, *args, **kwargs):
        """The page of the aggregation, with the services of its jobs.

        The serializer answers ``service`` of every row of this card. Neither
        a join into the aggregation nor an annotation naming the job of every
        grouped row may answer that: the aggregation groups the relations,
        and an expression over the job makes every grouped row pass through
        the job table - while only the handful of rows of one page shows the
        service at all (#1316). So one query over the jobs of the page adds
        the service to its rows after the pagination, and the aggregation
        reads the relation table alone.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is None:
            return Response(self.get_serializer(
                queryset, many=True).data)

        services = dict(
            HarvestingJob.objects.filter(
                pk__in={row["harvesting_job"] for row in page},
            ).values_list("pk", "service"),
        )
        for row in page:
            row["service"] = services.get(row["harvesting_job"])
        return self.get_paginated_response(
            self.get_serializer(page, many=True).data)
