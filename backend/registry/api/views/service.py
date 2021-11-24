from typing import OrderedDict

from rest_framework_json_api.schemas.openapi import AutoSchema
from registry.api.filters.service import OgcServiceFilterSet, WebFeatureServiceFilterSet, WebMapServiceFilterSet, FeatureTypeFilterSet, LayerFilterSet
from registry.api.serializers.jobs import TaskResultSerializer
from registry.tasks.service import build_ogc_service
from registry.api.serializers.service import OgcServiceCreateSerializer, OgcServiceSerializer, WebMapServiceSerializer, WebFeatureServiceSerializer, FeatureTypeSerializer, LayerSerializer
from registry.models import OgcService, WebMapService, Layer, WebFeatureService, FeatureType
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import RelationshipView, ModelViewSet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.settings import api_settings
from django_celery_results.models import TaskResult
from rest_framework.test import APIRequestFactory
from rest_framework.reverse import reverse


class WebMapServiceRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['WebMapServices'],
    )
    queryset = WebMapService.objects


class WebMapServiceViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['WebMapServices'],
    )
    queryset = WebMapService.objects.all()
    serializer_class = WebMapServiceSerializer
    prefetch_for_includes = {
        '__all__': [],
        'layers': ['layers']
    }
    filterset_class = WebMapServiceFilterSet


class LayerRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['WebMapService'],
    )
    queryset = Layer.objects


class LayerViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['WebMapServices'],
    )
    queryset = Layer.objects.all()
    serializer_class = LayerSerializer
    filterset_class = LayerFilterSet
    search_fields = ('id', 'title', 'abstract', 'keywords__keyword')
    prefetch_for_includes = {
        '__all__': [],
        'styles': ['styles'],
        'keywords': ['keywords']
    }

    def get_queryset(self):
        queryset = super(LayerViewSet, self).get_queryset()
        if 'service_pk' in self.kwargs:
            service_pk = self.kwargs['service_pk']
            queryset = queryset.filter(service__pk=service_pk)
        return queryset


class WebFeatureServiceRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['WebFeatureServices'],
    )
    queryset = WebFeatureService.objects


class WebFeatureServiceViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['WebFeatureServices'],
    )
    queryset = WebFeatureService.objects.all()
    serializer_class = WebFeatureServiceSerializer
    prefetch_for_includes = {
        '__all__': [],
        'featuretypes': ['featuretypes']
    }
    filterset_class = WebFeatureServiceFilterSet


class FeatureTypeRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['WebFeatureService'],
    )
    queryset = FeatureType.objects


class FeatureTypeViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['WebFeatureServices'],
    )
    queryset = FeatureType.objects.all()
    serializer_class = FeatureTypeSerializer
    filterset_class = FeatureTypeFilterSet

    prefetch_for_includes = {
        '__all__': [],
        'keywords': ['keywords']
    }

    def get_queryset(self):
        queryset = super(FeatureTypeViewSet, self).get_queryset()
        if 'service_pk' in self.kwargs:
            service_pk = self.kwargs['service_pk']
            queryset = queryset.filter(service__pk=service_pk)
        return queryset


class OgcServiceViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['OgcServices'],
    )
    queryset = OgcService.objects.all()
    serializer_classes = {
        'default': OgcServiceSerializer,
        'create': OgcServiceCreateSerializer
    }
    filterset_class = OgcServiceFilterSet
    search_fields = ('id', 'title', 'abstract', 'keywords__keyword')

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.serializer_classes['default'])

    def create(self, request, *args, **kwargs):
        # followed the jsonapi recommendation for async processing
        # https://jsonapi.org/recommendations/#asynchronous-processing
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task = build_ogc_service.delay(data=serializer.data)
        task_result, created = TaskResult.objects.get_or_create(task_id=task.id)

        # TODO: add auth information and other headers we need here
        dummy_request = APIRequestFactory().get(path=request.build_absolute_uri(reverse("registry:taskresult-detail", args=[task_result.pk])), data={})

        dummy_request.query_params = OrderedDict()
        # FIXME: wrong response data type is used. We need to set the resource_name to TaskResult here.
        serialized_task_result = TaskResultSerializer(task_result, **{'context': {'request': dummy_request}})
        serialized_task_result_data = serialized_task_result.data
        # meta object is None... we need to set it to an empty dict to prevend uncaught runtime exceptions
        if not serialized_task_result_data.get("meta", None):
            serialized_task_result_data.update({"meta": {}})

        headers = self.get_success_headers(serialized_task_result_data)

        return Response(serialized_task_result_data, status=status.HTTP_202_ACCEPTED, headers=headers)

    def get_success_headers(self, data):
        try:
            return {'Content-Location': str(data[api_settings.URL_FIELD_NAME])}
        except (TypeError, KeyError):
            return {}
