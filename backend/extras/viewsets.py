import json
from typing import OrderedDict

from django.db.models.query import Prefetch
from django.http import JsonResponse
from django.views.generic.detail import BaseDetailView, DetailView
from django_celery_results.models import TaskResult
from guardian.core import ObjectPermissionChecker
from notify.serializers import TaskResultSerializer
from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from rest_framework.viewsets import GenericViewSet
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import (AutoPrefetchMixin,
                                           PreloadIncludesMixin, RelatedMixin)


class ObjectPermissionCheckerViewSetMixin:
    """add a ObjectPermissionChecker based on the accessing user to the serializer context."""

    def get_serializer_context(self):
        """adds perm checker with prefetched permissions for objects of the current page to the serializer context."""
        context = super().get_serializer_context()
        if self.request:
            perm_checker: ObjectPermissionChecker = ObjectPermissionChecker(
                user_or_group=self.request.user)
            if not perm_checker._obj_perms_cache:
                objects = self.filter_queryset(
                    self.get_queryset().select_related(None).prefetch_related(None).only("pk"))
                if self.request.method == "GET":
                    objects = self.paginate_queryset(objects)

                perm_checker.prefetch_perms(objects)
            context.update({'perm_checker': perm_checker})
        return context


class HistoryInformationViewSetMixin:

    def get_prefetch_related(self, include):
        prefetch_related = super().get_prefetch_related(include)
        if prefetch_related:
            return prefetch_related
        elif include == "__all__":
            # TODO: better would be to extend the prefetch_related array
            return [
                Prefetch('change_logs', queryset=self.queryset.model.objects.filter_first_history(
                ), to_attr='first_history'),
                Prefetch('change_logs', queryset=self.queryset.model.objects.filter_last_history(
                ), to_attr='last_history')
            ]


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
            task_id=task.id, task_name=f"{task_function.__class__.__module__}.{task_function.__class__.__name__}"
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


class EmbeddedJsonDetailView(JSONResponseMixin, DetailView):
    template_name = "extras/embedded_json.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        _json = json.dumps(self.get_data(context=context), indent=3)
        context.update({"json": _json})
        return context


class NestedModelViewSet(
    NestedViewSetMixin, AutoPrefetchMixin, PreloadIncludesMixin, RelatedMixin, mixins.ListModelMixin,
        GenericViewSet
):
    """
    A viewset that provides default `list()` action for nested usage.
    """
    http_method_names = ["get", "head", "options"]
