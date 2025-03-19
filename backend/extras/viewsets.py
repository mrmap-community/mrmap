from typing import OrderedDict

from camel_converter import to_camel
from django.apps import apps
from django.db.models.query import Prefetch, QuerySet
from django.http import JsonResponse
from django.views.generic.detail import BaseDetailView
from django_celery_beat.models import CrontabSchedule
from django_celery_results.models import TaskResult
from extras.serializers import CrontabScheduleSerializer
from guardian.core import ObjectPermissionChecker
from notify.serializers import TaskResultSerializer
from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from rest_framework.viewsets import GenericViewSet
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.utils import get_resource_name
from rest_framework_json_api.views import (AutoPrefetchMixin, ModelViewSet,
                                           PreloadIncludesMixin, RelatedMixin)


class ObjectPermissionCheckerViewSetMixin:
    """add a ObjectPermissionChecker based on the accessing user to the serializer context."""

    def get_serializer_context(self):
        """adds perm checker with prefetched permissions for objects of the current page to the serializer context."""
        context = super().get_serializer_context()

        # we use the leat modified queryset here to check permissions...
        queryset = self.queryset
        if isinstance(queryset, QuerySet):
            # Ensure queryset is re-evaluated on each request.
            queryset = queryset.all()

        if self.request:
            perm_checker: ObjectPermissionChecker = ObjectPermissionChecker(
                user_or_group=self.request.user)
            if not perm_checker._obj_perms_cache:

                objects = self.filter_queryset(
                    queryset.select_related(None).prefetch_related(None).only("pk"))
                # if self.request.method == "GET":
                if self.action == 'list':

                    objects = self.paginate_queryset(objects)
                if objects:
                    perm_checker.prefetch_perms(objects)
            context.update({'perm_checker': perm_checker})
        return context


class HistoryInformationViewSetMixin:

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        try:
            django_model = apps.get_model(
                self.queryset.model._meta.app_label, f"Historical{self.queryset.model.__name__}")

            qs = qs.prefetch_related(
                Prefetch(
                    'change_logs',
                    queryset=django_model.objects.filter(
                        history_type='+').select_related("history_user").only('history_relation', 'history_user__id', 'history_date')[:1],
                    to_attr='first_history'
                ),
                Prefetch(
                    'change_logs',
                    queryset=django_model.objects.select_related(
                        "history_user").order_by('-history_date').only('history_relation', 'history_user__id', 'history_date')[:1],
                    to_attr='last_history'
                )
            )
        except LookupError:
            pass
        return qs


class SerializerClassesMixin:
    def get_serializer_class(self):
        serializer = self.serializer_classes.get(
            self.action, self.serializer_classes.get(
                "default", None)
        )
        if not serializer:
            serializer = super().get_serializer_class()
        return serializer


class AsyncCreateMixin:
    task_function = None

    def get_task_function(self):
        return self.task_function

    def get_task_kwargs(self, request, serializer):
        raise NotImplementedError

    def create(self, request, *args, **kwargs):
        # followed the jsonapi recommendation for async processing
        # https://jsonapi.org/recommendations/#asynchronous-processing
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task_function = self.get_task_function()
        task = self.get_task_function().delay(
            **self.get_task_kwargs(request=request, serializer=serializer))
        task_result, created = TaskResult.objects.get_or_create(
            task_id=task.id, task_name=f"{task_function.__class__.__module__}.{
                task_function.__class__.__name__}"
        )

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


class JSONResponseMixin:
    """
    A mixin that can be used to render a JSON response.
    """

    def render_to_json_response(self, context, **response_kwargs):
        """
        Returns a JSON response, transforming 'context' to make the payload.
        """
        return JsonResponse(
            self.get_data(context),
            **response_kwargs
        )

    def get_data(self, context):
        """
        Returns an object that will be serialized as JSON by json.dumps().
        """
        # Note: This is *EXTREMELY* naive; in reality, you'll need
        # to do much more complex handling to ensure that arbitrary
        # objects -- such as Django model instances or querysets
        # -- can be serialized as JSON.
        return context


class JSONDetailView(JSONResponseMixin, BaseDetailView):
    def render_to_response(self, context, **response_kwargs):
        return self.render_to_json_response(context, **response_kwargs)


class PreloadNotIncludesMixin:
    def get_prefetch_for_not_includes(self):
        return getattr(self, "prefetch_for_not_includes", {})

    def get_prefetch_related_for_not_includes(self, include):
        return self.get_prefetch_for_not_includes().get(include, None)

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)

        resource_name = get_resource_name({"view": self})
        if not resource_name:
            return qs

        include = self.request.GET.get("include", None)
        fields_snake = self.request.GET.get(
            f"fields[{resource_name}]", "").split(',')
        fields = [to_camel(field) for field in fields_snake if field.strip()]

        for key in list(self.get_prefetch_for_not_includes().keys()) + ['__all__']:
            prefetch_related = self.get_prefetch_related_for_not_includes(key)

            field_list = [x for x in key.split(',') if x.strip()]

            if (prefetch_related is not None) and \
                (not include or key not in include) and \
                    (not fields or any(field in fields for field in field_list)):
                qs = qs.prefetch_related(*prefetch_related)
        return qs


class SparseFieldMixin:
    def initial(self, *args, **kwargs):
        # todo: get all sparsefield parameters
        fields_snake = self.request.GET.get(
            f"fields[{self.queryset.model.__name__}]", "").split(',')
        self.sparse_fields = {
            self.queryset.model.__name__: [
                to_camel(field) for field in fields_snake if field.strip()]
        }
        super().initial(*args, **kwargs)

    def get_sparse_fields(self, resource):
        return self.sparse_fields.get(resource, [])

    def check_sparse_fields_contains(self, fieldname):
        fields = self.get_sparse_fields(self.queryset.model.__name__)
        return not fields or fieldname in fields


class NestedModelViewSet(
    NestedViewSetMixin, AutoPrefetchMixin, PreloadIncludesMixin, RelatedMixin, mixins.ListModelMixin,
        GenericViewSet
):
    """
    A viewset that provides default `list()` action for nested usage.
    """
    http_method_names = ["get", "head", "options"]


class CrontabScheduleViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `WebMapServiceMonitoringSetting`

        create:
            Endpoint to register new `WebMapServiceMonitoringSetting` object
        list:
            Retrieves all registered `WebMapServiceMonitoringSetting` objects
        retrieve:
            Retrieve one specific `WebMapServiceMonitoringSetting` by the given id
        partial_update:
            Endpoint to update some fields of a `WebMapServiceMonitoringSetting`
        destroy:
            Endpoint to remove a registered `WebMapServiceMonitoringSetting` from the system
    """
    queryset = CrontabSchedule.objects.all()
    serializer_class = CrontabScheduleSerializer

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'minute': ['exact', 'icontains', 'contains'],
        'hour': ['exact', 'icontains', 'contains'],
        'day_of_month': ['exact', 'icontains', 'contains'],
        'month_of_year': ['exact', 'icontains', 'contains'],
        'day_of_week': ['exact', 'icontains', 'contains'],
        # 'timezone': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id",)
    ordering_fields = [
        "id",
        "minute",
        "hour",
        "day_of_month",
        "month_of_year",
        "day_of_week",
        # "timezone"
    ]
