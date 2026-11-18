import uuid
from collections import OrderedDict

from camel_converter import to_camel, to_snake
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.db.models.query import Prefetch, QuerySet
from django.http import Http404, JsonResponse
from django.views.generic.detail import BaseDetailView
from drf_spectacular.utils import extend_schema
from extras.permissions import (DjangoObjectPermissionsOrAnonReadOnly,
                                list_is_permission_filtered,
                                objects_for_user)
from extras.utils import get_sparse_fields
from guardian.core import ObjectPermissionChecker
from notify.serializers import BackgroundProcessSerializer
from simple_history.utils import (get_app_model_primary_key_name,
                                  get_history_manager_for_model)
from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from rest_framework.viewsets import GenericViewSet
from rest_framework_json_api.utils import (get_included_resources,
                                           get_resource_name)
from rest_framework_json_api.views import PreloadIncludesMixin, RelatedMixin


class ObjectPermissionCheckerViewSetMixin:
    """add a ObjectPermissionChecker based on the accessing user to the serializer context."""

    #: the object which a detail action answers, remembered by `get_object`
    #: below so that the permissions are prefetched for exactly this object
    object = None

    # the objects the answer was already selected with, remembered by
    # `paginate_queryset` so that the permissions are prefetched for exactly
    # the objects the answer shows, without asking the database again
    page_for_permissions = None

    def get_object(self):
        """Read the object of a detail action and remember it on the view.

        DRF hands the object which `get_object` reads to the serializer but
        does not keep it on the view. Without this memory the serializer
        context cannot tell which object a detail action answers and falls
        back to asking the whole queryset of the viewset which objects it
        should prefetch permissions for - which evaluates the queryset of the
        viewset as a whole on every detail request, annotations and all, and
        turned into 18.7 s per detail request as soon as the alerts of the
        services were annotated to it (#1308).
        """
        self.object = super().get_object()
        return self.object

    def paginate_queryset(self, queryset, *args, **kwargs):
        """Remember the objects of the page the answer shows.

        A list action already filters and slices the queryset to read its
        page. The permissions are prefetched for these very objects instead
        of filtering and paginating the queryset a second time, which would
        answer a second COUNT and select the page a second time.
        """
        page = super().paginate_queryset(queryset, *args, **kwargs)
        self.page_for_permissions = page if page is not None else queryset
        return page

    def get_serializer_context(self):
        """adds perm checker with prefetched permissions for objects of the current page to the serializer context."""
        context = super().get_serializer_context()

        # we use the leat modified queryset here to check permissions...
        queryset = self.queryset
        if isinstance(queryset, QuerySet):
            # Ensure queryset is re-evaluated on each request.
            queryset = queryset.all()

        """
        Skip object-permission checker setup for drf-spectacular's fake schema views. Schema introspection only needs serializer metadata, so querying and prefetching object permissions for every discovered endpoint is unnecessary. This keeps normal request permission checks unchanged and adds a regression test for the schema path.
        """
        if self.request and not getattr(self, 'swagger_fake_view', False):
            perm_checker: ObjectPermissionChecker = ObjectPermissionChecker(
                user_or_group=self.request.user)
            if not perm_checker._obj_perms_cache:
                if self.action == 'list' and \
                        self.page_for_permissions is not None:
                    # `paginate_queryset` already selected and read the page
                    objects = self.page_for_permissions
                elif getattr(self, 'object', None) is not None:
                    # a detail action answers one object which it has read
                    # into self.object
                    objects = [self.object]
                elif self.action == 'create':
                    # the object a create answers did not exist when the
                    # serializer was built, nothing can be prefetched for it
                    objects = []
                else:
                    # Include filters may add prefetches; permission checks only need ids.
                    objects = self.filter_queryset(queryset).select_related(
                        None).prefetch_related(None).only("pk")
                if objects:
                    perm_checker.prefetch_perms(objects)
            # the json:api renderer does not hand the serializer context to the
            # serializers of included resources but only the view, so the checker
            # has to be reachable through the view for objects of this model
            self.perm_checker = perm_checker
            self.perm_checker_model = queryset.model
            context.update({'perm_checker': perm_checker})
        return context


class HistoryInformationViewSetMixin:

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        # FUTURE: only needed if sparsefields contains created_by, created_at, updated_by or updated_at. We need to check this to prevent unnecessary prefetching.
        try:
            sparse_fields = get_sparse_fields(self.request)
            resource_based_sparse_fields = sparse_fields.get(
                self.queryset.model.__name__, [])
            # an include is written with the field names of the api, the
            # relations of a model are named with the names of python
            include_resources_param = [
                to_snake(include) for include in get_included_resources(
                    self.request, self.get_serializer_class())]

            HistoryModel = apps.get_model(
                self.queryset.model._meta.app_label,
                f"Historical{self.queryset.model.__name__}"
            )
            prefetches = []
            # created_by and last_modified_by always dereference the user of the
            # history record, so the user is always joined. A history row carries
            # a copy of every column of the object it belongs to, so only the
            # columns of the history fields are loaded for the other case.
            user_is_included = "created_by" in include_resources_param \
                or "last_modified_by" in include_resources_param
            only_for_history = ['history_relation', 'history_date',
                                'history_user']

            if not resource_based_sparse_fields \
                    or any(field in ["created_at", "created_by"] for field in resource_based_sparse_fields)\
                    or "created_by" in include_resources_param:
                prefetch_qs = HistoryModel.objects.filter(
                    history_type='+').select_related('history_user')
                if not user_is_included:
                    prefetch_qs = prefetch_qs.only(*only_for_history)
                prefetches.append(
                    Prefetch(
                        'change_logs',
                        queryset=prefetch_qs[:1],
                        to_attr='first_history'
                    )
                )
            if not resource_based_sparse_fields \
                    or any(field in ["last_modified_at", "last_modified_by"] for field in resource_based_sparse_fields)\
                    or "last_modified_by" in include_resources_param:

                prefetch_qs = HistoryModel.objects.all().select_related(
                    'history_user')
                if not user_is_included:
                    prefetch_qs = prefetch_qs.only(*only_for_history)
                prefetches.append(
                    Prefetch(
                        'change_logs',
                        queryset=prefetch_qs[:1],
                        to_attr='last_history'
                    )
                )

            if prefetches:
                qs = qs.prefetch_related(*prefetches)

        except LookupError:
            pass
        return qs


class HistoricalViewSetMixin:
    """The read-only api over the audit trail of one model (#741).

    A changelog is not an ordinary resource: it is written by the flows which
    change the object, never by a request. ``http_method_names`` therefore
    carries no write verb at all — #1449 removed ``patch`` for exactly that
    reason, and #741 keeps it that way for the role tables, whose audit rows
    are the answer to "who decided this?" and must not be editable by whoever
    asks.

    The one thing every consumer of a changelog asks beside the row itself is
    *what changed*: ``diff_against`` needs the row which came before. Reading
    that per record is one query per row, so the previous row is annotated here
    and the page's rows are fetched in one ``in_bulk`` — the plan is stated
    once for every model which keeps history rather than rewritten per screen.
    """

    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    # #1449: patch is gone as well. No flow edits an audit row — the frontend only
    # reads the changelog — and leaving the verb open let any authenticated caller
    # rewrite the compliance record the history exists to prove (#741).
    http_method_names = ["get", "head", "options"]
    # reads stay open the way list_HistoricalWebMapServices.feature pins them;
    # the gate answers per object, so a write could only ever be answered by an
    # object grant over the audit row — and since patch left http_method_names,
    # no request reaches that decision anymore.
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    select_for_includes = {
        "historyUser": ["history_user"],
        # "historyRelation": ["history_relation"]
    }
    ordering_fields = ["id", 'history_date', 'history_user']

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)

        include = self.request.GET.get("include", None)

        if not include or "historyUser" not in include:
            defer = [
                f"history_user__{field.name}"
                for field in get_user_model()._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("history_user").defer(*defer)
        else:
            # FUTURE: select_for_includes setup does not work for history records...
            qs = qs.select_related("history_user")

        # At the end of the existing get_queryset(), before returning qs:
        original_model = qs.model.instance_type
        key_name = get_app_model_primary_key_name(original_model)

        previous_records = (
            get_history_manager_for_model(original_model)
            .using(qs.db)
            .filter(
                **{
                    key_name: OuterRef(key_name),
                    "history_date__lt": OuterRef("history_date"),
                }
            )
            .order_by("-history_date")
        )

        return qs.annotate(
            prev_record_id=Subquery(
                previous_records.values("history_id")[:1]
            )
        )

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        if page is None:
            return None

        previous_ids = {
            record.prev_record_id
            for record in page
            if record.prev_record_id is not None
        }

        previous_by_id = (
            queryset.model._default_manager
            .using(queryset.db)
            .in_bulk(previous_ids)
            if previous_ids
            else {}
        )

        for record in page:
            record.prev_prefetched_record = previous_by_id.get(
                record.prev_record_id
            )

        return page


class PermissionVisibilityMixin:
    """Answers the visibility tri-state of the resources a viewset reads.

    The annotation is applied always: every screen, list and detail alike,
    learns whether a resource is public, organization-internal or restricted
    from one derived value, without a query per object (#739).

    Whether the list itself is filtered by that value is a rollout decision
    per model, taken in `PERMISSION_FILTERED_LIST_MODELS`: while a model is
    not named there, the list keeps answering what it answers today and only
    the detail route is held to the permission boundary. Models whose rows
    carry an `owner` org are the ones the org-axis of `objects_for_user`
    understands; `accounts.checks` refuses naming anything else.
    """

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            # drf-spectacular builds a throw-away view to read the schema;
            # it has no user and must not hit the database
            return qs
        model = qs.model
        if list_is_permission_filtered(model):
            # narrowed first, on the plain queryset: the facade OR-composes
            # its axes and every axis starts from the queryset it was handed,
            # which is the shape its own callers pass
            qs = objects_for_user(
                self.request.user,
                f"{model._meta.app_label}.view_{model._meta.model_name}",
                qs)
        # annotated last: the answer belongs to the rows which survived, and
        # it costs no query of its own
        return qs.with_visibility()


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
    """Answers a create whose work is done by a background process.

    The viewset creates the process in `get_task_kwargs` and hands it back
    together with the kwargs of the task; the process is what the client
    polls: its status answers the queued, running and terminal states, its
    related resource names the service as soon as one exists and its logs
    carry what went wrong. The process is written before the message goes
    out, so the answer of this POST always points at a resource which exists
    (#1177).

    The `TaskResult` answer which this mixin gave before is retired with
    D01/B of #1175: a registration no longer leaves a row of that table
    behind. The id of the task which this publication publishes is decided
    and registered with the process before the message goes out, so an abort
    issued right after the answer can revoke the task by that id although no
    worker has read the message yet (#1179).
    """

    task_function = None

    def get_task_function(self):
        return self.task_function

    def get_task_kwargs(self, request, serializer):
        """The background process and the kwargs to publish its task with.

        Returns:
            tuple: (BackgroundProcess, dict) — the process which answers how
                the work goes and the kwargs handed to the task.
        """
        raise NotImplementedError

    @extend_schema(
        responses={(202, "application/vnd.api+json"): BackgroundProcessSerializer})
    def create(self, request, *args, **kwargs):
        # followed the jsonapi recommendation for async processing
        # https://jsonapi.org/recommendations/#asynchronous-processing
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task_function = self.get_task_function()
        background_process, task_kwargs = self.get_task_kwargs(
            request=request, serializer=serializer)

        # The id of the message is decided here, and stored with the process,
        # before the message goes out: an abort issued right after this answer
        # finds the task by that id although no worker has read the message
        # yet (#1179). The process owns the id directly - not a row of the
        # retired `TaskResult` table.
        task_id = uuid.uuid4()
        background_process.append_celery_task_ids([task_id])
        task_function.apply_async(
            kwargs=task_kwargs, task_id=str(task_id))

        # FUTURE: add auth information and other headers we need here
        dummy_request = APIRequestFactory().get(
            path=request.build_absolute_uri(
                reverse("notify:backgroundprocess-detail",
                        args=[background_process.pk])
            ),
            data={},
        )

        dummy_request.query_params = OrderedDict()
        serialized_process_data = BackgroundProcessSerializer(
            background_process, **{"context": {"request": dummy_request}}
        ).data

        # the json:api renderer asks the view which type of resource the
        # answer carries; this answer is a process, not the resource the
        # create of this endpoint otherwise deals with (#1177)
        self.resource_name = \
            BackgroundProcessSerializer.Meta.model.__name__

        headers = self.get_success_headers(serialized_process_data)

        return Response(
            serialized_process_data,
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


class ExtendedPreloadIncludesMixin:
    def _resolve_prefetches(self, prefetches):
        """
        Resolve prefetch definitions:
        - callables (e.g. lambda: Prefetch(...)) werden aufgerufen
        - Strings und Prefetch-Objekte bleiben unverändert
        """
        resolved = []
        for p in prefetches:
            if callable(p):
                resolved.append(p(self.request))
            else:
                resolved.append(p)
        return resolved

    def get_prefetch_related(self, include):
        raw = super().get_prefetch_related(include)
        if raw is not None:
            return self._resolve_prefetches(raw)
        return None


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

        # an include is written with the field names of the api, the keys of
        # prefetch_for_includes and prefetch_for_not_includes are the names of
        # the relations of the model
        included_resources = [
            to_snake(include) for include in get_included_resources(
                self.request, self.get_serializer_class())]

        # A sparse fieldset is written with the field names of the api, the keys
        # of prefetch_for_not_includes are the names of python.
        # extras.utils.parse_sparse_fieldsets turns one into the other.
        fields = get_sparse_fields(self.request).get(resource_name, [])

        for key in list(self.get_prefetch_for_not_includes().keys()) + ['__all__']:
            prefetch_related = self.get_prefetch_related_for_not_includes(key)

            field_list = [x for x in key.split(',') if x.strip()]

            if (prefetch_related is not None) and \
                (not included_resources or key not in included_resources) and \
                    (not fields or any(field in fields for field in field_list)):
                qs = qs.prefetch_related(*prefetch_related)
        return qs


class SparseFieldMixin:
    def initial(self, *args, **kwargs):
        # FUTURE: get all sparsefield parameters
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


class NestedViewSetMixin:
    def get_queryset(self):
        return self.filter_queryset_by_parents_lookups(
            super().get_queryset()
        )

    def filter_queryset_by_parents_lookups(self, queryset):
        parents_query_dict = self.get_parents_query_dict()
        if parents_query_dict:
            try:
                # Try to validate UUID fields before filtering
                cleaned_dict = {}
                for key, value in parents_query_dict.items():
                    if 'uuid' in key.lower() or key.endswith('_code'):
                        try:
                            # Try to validate as UUID
                            cleaned_dict[key] = uuid.UUID(str(value))
                        except ValueError:
                            raise Http404
                    else:
                        cleaned_dict[key] = value
                return queryset.filter(**cleaned_dict)
            except (ValueError, ValidationError):
                raise Http404
        else:
            return queryset

    def get_parents_query_dict(self):
        result = {}
        for kwarg_name, kwarg_value in self.kwargs.items():
            if kwarg_name.startswith('parent_lookup_'):
                query_lookup = kwarg_name.replace(
                    'parent_lookup_',
                    '',
                    1
                )
                query_value = kwarg_value
                result[query_lookup] = query_value
        return result


class NestedModelViewSet(
    NestedViewSetMixin, PreloadIncludesMixin, RelatedMixin, mixins.ListModelMixin,
        GenericViewSet
):
    """
    A viewset that provides default `list()` action for nested usage.
    """
    http_method_names = ["get", "head", "options"]
