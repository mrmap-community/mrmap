from typing import OrderedDict

from django_celery_results.models import TaskResult
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import ObjectPermissionCheckerViewSetMixin
from notify.serializers import TaskResultSerializer
from registry.filters.service import (FeatureTypeFilterSet, LayerFilterSet,
                                      WebFeatureServiceFilterSet,
                                      WebMapServiceFilterSet)
from registry.models import (FeatureType, Layer, WebFeatureService,
                             WebMapService)
from registry.serializers.service import (FeatureTypeSerializer,
                                          LayerSerializer,
                                          WebFeatureServiceCreateSerializer,
                                          WebFeatureServiceSerializer,
                                          WebMapServiceCreateSerializer,
                                          WebMapServiceSerializer)
from registry.tasks.service import build_ogc_service
from rest_framework import status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet, RelationshipView


class OgcServiceCreateMixin:

    def get_serializer_class(self):
        return self.serializer_classes.get(
            self.action, self.serializer_classes["default"]
        )

    def create(self, request, *args, **kwargs):
        # followed the jsonapi recommendation for async processing
        # https://jsonapi.org/recommendations/#asynchronous-processing
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task = build_ogc_service.delay(get_capabilities_url=serializer.validated_data['get_capabilities_url'],
                                       collect_metadata_records=serializer.validated_data[
                                           'collect_metadata_records'],
                                       service_auth_pk=serializer.service_auth.id if hasattr(
                                           serializer, 'service_auth') else None,
                                       **{'request': {'path': request.path, 'method': request.method, 'content_type': request.content_type, 'data': request.GET, 'user_pk': request.user.pk}})
        task_result, created = TaskResult.objects.get_or_create(
            task_id=task.id,
            task_name='registry.tasks.service.build_ogc_service')

        # TODO: add auth information and other headers we need here
        dummy_request = APIRequestFactory().get(
            path=request.build_absolute_uri(
                reverse("notify:taskresult-detail", args=[task_result.pk])
            ),
            data={},
        )

        dummy_request.query_params = OrderedDict()
        # FIXME: wrong response data type is used. We need to set the resource_name to TaskResult here.
        serialized_task_result = TaskResultSerializer(
            task_result, **{"context": {"request": dummy_request}}
        )
        serialized_task_result_data = serialized_task_result.data
        # meta object is None... we need to set it to an empty dict to prevend uncaught runtime exceptions
        if not serialized_task_result_data.get("meta", None):
            serialized_task_result_data.update({"meta": {}})

        headers = self.get_success_headers(serialized_task_result_data)

        return Response(
            serialized_task_result_data,
            status=status.HTTP_202_ACCEPTED,
            headers=headers,
        )

    def get_success_headers(self, data):
        try:
            return {"Content-Location": str(data[api_settings.URL_FIELD_NAME])}
        except (TypeError, KeyError):
            return {}


class WebMapServiceRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=["WebMapService"],
    )
    queryset = WebMapService.objects
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class WebMapServiceViewSet(ObjectPermissionCheckerViewSetMixin, NestedViewSetMixin, OgcServiceCreateMixin, ModelViewSet):
    schema = AutoSchema(
        tags=["WebMapService"],
    )
    queryset = WebMapService.objects.with_meta()
    serializer_classes = {
        "default": WebMapServiceSerializer,
        "create": WebMapServiceCreateSerializer
    }
    prefetch_for_includes = {
        "__all__": [],
        # "layers": ["layers"],
        # "keywords": ["keywords"],
        # "created_by": [Prefetch('history', queryset=WebMapService.history.select_related('history_user').filter(history_type='+'), to_attr='first_history')]
    }
    filterset_class = WebMapServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class LayerRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=["WebMapService"],
    )
    queryset = Layer.objects
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class LayerViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=["WebMapService"],
    )
    queryset = Layer.objects.all()
    serializer_class = LayerSerializer
    filterset_class = LayerFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    prefetch_for_includes = {
        "__all__": [],
        "styles": ["styles"],
        "keywords": ["keywords"],
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    # FIXME: first_history is not an attribute of the objects...

    # def get_queryset(self):
    #     qs = super().get_queryset()
    #     prefetch_ordered_histories = Prefetch('history', queryset=Layer.change_log.order_by(
    #         '-history_date'), to_attr='ordered_histories')
    #     qs.prefetch_related(prefetch_ordered_histories)
    #     return qs


class WebFeatureServiceRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=["WebFeatureService"],
    )
    queryset = WebFeatureService.objects
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class WebFeatureServiceViewSet(ObjectPermissionCheckerViewSetMixin, NestedViewSetMixin, OgcServiceCreateMixin, ModelViewSet):
    schema = AutoSchema(
        tags=["WebFeatureService"],
    )
    queryset = WebFeatureService.objects.with_meta()
    serializer_classes = {
        "default": WebFeatureServiceSerializer,
        "create": WebFeatureServiceCreateSerializer,
    }
    prefetch_for_includes = {"__all__": [], "featuretypes": ["featuretypes"]}
    filterset_class = WebFeatureServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class FeatureTypeRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=["WebFeatureService"],
    )
    queryset = FeatureType.objects
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class FeatureTypeViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=["WebFeatureService"],
    )
    queryset = FeatureType.objects.all()
    serializer_class = FeatureTypeSerializer
    filterset_class = FeatureTypeFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")

    prefetch_for_includes = {"__all__": [], "keywords": ["keywords"]}
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
