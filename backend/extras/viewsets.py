from typing import OrderedDict

from django.db.models.query import Prefetch
from django_celery_results.models import TaskResult
from guardian.core import ObjectPermissionChecker
from notify.serializers import TaskResultSerializer
from rest_framework import status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory


class ObjectPermissionCheckerViewSetMixin:
    """add a ObjectPermissionChecker based on the accessing user to the serializer context."""

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request:
            perm_checker = ObjectPermissionChecker(
                user_or_group=self.request.user)
            perm_checker.prefetch_perms(
                self.get_queryset().prefetch_related(None))
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
        return self.serializer_classes.get(
            self.action, self.serializer_classes.get(
                "default", super().get_serializer_class())
        )


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
            **self.get_task_kwargs(serializer=serializer))
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
