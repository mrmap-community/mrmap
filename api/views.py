# Create your views here.
from django.utils import timezone
from collections import OrderedDict

from celery.result import AsyncResult
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from MrMap import utils
from MrMap.decorator import check_permission, resolve_metadata_public_id
from MrMap.messages import SERVICE_NOT_FOUND, PARAMETER_ERROR, \
    RESOURCE_NOT_FOUND, SERVICE_REMOVED
from MrMap.responses import DefaultContext, APIResponse
from api import view_helper
from monitoring.models import Monitoring, MonitoringRun
from api.forms import TokenForm
from api.permissions import CanRegisterService, CanRemoveService, CanActivateService

from api.serializers import ServiceSerializer, LayerSerializer, OrganizationSerializer, GroupSerializer, \
    MetadataSerializer, CatalogueMetadataSerializer, PendingTaskSerializer, CategorySerializer, \
    MonitoringSerializer, MonitoringSummarySerializer, serialize_catalogue_metadata
from api.settings import API_CACHE_TIME, API_ALLOWED_HTTP_METHODS, CATALOGUE_DEFAULT_ORDER, SERVICE_DEFAULT_ORDER, \
    LAYER_DEFAULT_ORDER, ORGANIZATION_DEFAULT_ORDER, METADATA_DEFAULT_ORDER, GROUP_DEFAULT_ORDER, \
    SUGGESTIONS_MAX_RESULTS, API_CACHE_KEY_PREFIX
from service import tasks
from service.helper import service_helper
from service.models import Service, Layer, Metadata, Keyword, Category
from service.settings import DEFAULT_SRS_STRING
from structure.models import Organization, MrMapGroup, Permission, PendingTask
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper


def menu_view(request: HttpRequest):
    """ The API menu view where settings for the remote access can be set.

    Args:
        request (HttpRequest): The incoming request
    Returns:
         rendered view
    """
    template = "views/api_menu.html"
    token_form = TokenForm(request.POST)
    user = user_helper.get_user(request)

    if not user.is_authenticated:
        return redirect("login")

    # Get user token
    try:
        token = Token.objects.get(
            user=user
        )
    except ObjectDoesNotExist:
        # User has no token yet
        token = None

    if token is not None:
        token_form = TokenForm(instance=token)

    token_form.action_url = reverse("api:generate-token")
    params = {
        "form": token_form,
    }
    default_context = DefaultContext(request, params, user)
    return render(request, template, default_context.get_context())


@check_permission(
    PermissionEnum.CAN_GENERATE_API_TOKEN
)
def generate_token(request: HttpRequest):
    """ Generates a token for the user.

    Returns after finished work back to the menu page

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A redirect to a view
    """
    if request.method == "POST":
        user = user_helper.get_user(request)
        # Get user token
        try:
            token = Token.objects.get(
                user=user
            )
        except ObjectDoesNotExist:
            # User has no token yet
            token = None

        # Remove the given key.
        # Otherwise the is_valid() would fail, since the key for this user could already exists.
        # We are only interested in the csrf token validation.
        post_dict = request.POST.dict()
        post_dict["key"] = ""
        token_form = TokenForm(post_dict)

        if not token_form.is_valid():
            return HttpResponse(status=403)

        # Generate new access token, old token can not be reused, must be deleted
        if token is not None:
            token.delete()
        token = Token(user=user)
        token.save()

    # Redirect user directly to the same page. Why?
    # This way, we make sure the user does not re-generate another token accidentally by pressing F5 or reload,
    # or whatever. We force the GET way.
    return redirect("api:menu")


class APIPagination(PageNumberPagination):
    """ Pagination class for this API

    Overwrites the default PageNumberPagination such that the following GET parameters can be used to
    modify the pagination style:

        rpp (int): Number of results per page

    """
    page_size_query_param = "rpp"


class PendingTaskViewSet(viewsets.GenericViewSet):
    """ ViewSet for PendingTask records

    """
    serializer_class = PendingTaskSerializer
    http_method_names = ["get"]
    pagination_class = APIPagination

    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, pk=None):
        """ Returns a single PendingTask record information

        Args:
            request (HttpRequet): The incoming request
            pk (int): The primary_key (id) of the PendingTask
        Returns:
             response (Response): Contains the json serialized information about the pending task
        """
        response = APIResponse()
        try:
            tmp = PendingTask.objects.get(id=pk)
            celery_task = AsyncResult(tmp.task_id)
            progress = float(celery_task.info.get("current", -1))
            serializer = PendingTaskSerializer(tmp)

            response.data.update(serializer.data)
            response.data["progress"] = progress
            response.data["success"] = True
        except ObjectDoesNotExist:
            response.data["msg"] = RESOURCE_NOT_FOUND
        return Response(data=response.data)


class ServiceViewSet(viewsets.GenericViewSet):
    """ Overview of all services matching the given parameters

        Query parameters:

            type:   optional, 'wms' or 'wfs'
            q:      optional, search in abstract, title and keywords for a match
            orgid:  optional, search for layers which are published by this organization (id)
            order:  optional, orders by an attribute (e.g. id, uuid, ..., default is id)
            rpp:    optional, Number of results per page

    """
    serializer_class = ServiceSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS + ["delete"]
    pagination_class = APIPagination

    permission_classes = (
        IsAuthenticated,
        CanRegisterService,
        CanRemoveService,
        CanActivateService,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable_fields = [field.name for field in Service._meta.fields]

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Service.objects.filter(
            metadata__is_active=True,
            is_root=True
        )

        """ Layer as service is deactivated, since there is an own layer API
        
        # filter by service or service+layers
        las = self.request.query_params.get("las", False)
        las = utils.resolve_boolean_attribute_val(las)
        if not las:
            self.queryset = self.queryset.filter(
                is_root=False
            )
        """

        # filter by type
        service_type = self.request.query_params.get("type", None)
        self.queryset = view_helper.filter_queryset_service_type(self.queryset, service_type)

        # filter by query (title and abstract)
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_service_query(self.queryset, query)

        # filter by organization
        org = self.request.query_params.get("orgid", None)
        self.queryset = view_helper.filter_queryset_services_organization_id(self.queryset, org)

        # filter by uuid
        uuid = self.request.query_params.get("uuid", None)
        self.queryset = view_helper.filter_queryset_services_uuid(self.queryset, uuid)

        # order by
        order_by = self.request.query_params.get("order", SERVICE_DEFAULT_ORDER)
        if order_by not in self.orderable_fields:
            order_by = SERVICE_DEFAULT_ORDER
        self.queryset = view_helper.order_queryset(self.queryset, order_by)

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = ServiceSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        """ Creates a new service

        Args:
            request (HttpRequest): The incoming request
        Returns:
             response (Response)
        """
        service_serializer = ServiceSerializer()
        params = request.POST.dict()
        pending_task = service_serializer.create(validated_data=params, request=request)

        response = APIResponse()
        response.data["success"] = pending_task is not None
        response.data["pending_task_id"] = pending_task.id
        if pending_task:
            status = 200
        else:
            status = 500
        response = Response(data=response.data, status=status)
        return response

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def retrieve(self, request, pk=None):
        try:
            tmp = Layer.objects.get(metadata__id=pk)
            if not tmp.metadata.is_active:
                return Response(status=423)
            serializer = LayerSerializer(tmp)
        except ObjectDoesNotExist:
            try:
                tmp = Service.objects.get(metadata__id=pk)
                if not tmp.metadata.is_active:
                    return Response(status=423)
                serializer = ServiceSerializer(tmp)
            except ObjectDoesNotExist:
                return Response(RESOURCE_NOT_FOUND, status=404)

        return Response(serializer.data)

    @action(methods=["post"], detail=True, url_path="active-state")
    def active_state(self, request, pk=None):
        """ Activates a service via remote access

        Args:
            request: The incoming request
            pk: The service id
        Returns:
             Response
        """
        user = user_helper.get_user(request)
        parameter_name = "active"
        new_status = request.POST.dict().get(parameter_name, None)
        new_status = utils.resolve_boolean_attribute_val(new_status)

        response = APIResponse()
        if new_status is None or not isinstance(new_status, bool):
            response.data["msg"] = PARAMETER_ERROR.format(parameter_name)
            return Response(data=response.data, status=500)

        try:
            md = Metadata.objects.get(service__id=pk)

            response.data["oldStatus"] = md.is_active

            md.is_active = new_status
            md.save()
            # run activation async!
            tasks.async_activate_service.delay(pk, user.id, new_status)
            response.data["newStatus"] = md.is_active
            response.data["success"] = True
            return Response(data=response.data, status=200)
        except ObjectDoesNotExist:
            response.data["msg"] = SERVICE_NOT_FOUND
            return Response(data=response.data, status=404)

    def update(self, request, pk=None):
        # Not supported
        pass

    def partial_update(self, request, pk=None):
        # Not supported
        pass

    def destroy(self, request, pk=None):
        """ Deletes a service which is identified by its metadata record's primary_key pk

        Args:
            request (HttpRequest): The incoming request
            pk (int): The primary key (id)
        Returns:
             Response
        """
        # Use the already existing internal deleting of services
        response = APIResponse()
        try:
            md = Metadata.objects.get(id=pk)
            user = user_helper.get_user(request)
            service_helper.remove_service(md, user)
            response.data["success"] = True
            response.data["msg"] = SERVICE_REMOVED
        except ObjectDoesNotExist:
            response.data["success"] = False
            response.data["msg"] = RESOURCE_NOT_FOUND
        return Response(data=response.data)


class LayerViewSet(viewsets.GenericViewSet):
    """ Overview of all layers matching the given parameters

        Query parameters:
            pid:    optional, refers to the parent service id
            q:      optional, search in abstract, title and keywords for a match
            orgid:  optional, search for layers which are published by this organization (id)
            order:  optional, orders by an attribute (e.g. id, identifier, ..., default is id)
            rpp:    optional, Number of results per page
    """

    serializer_class = LayerSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    permission_classes = (IsAuthenticated,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable_fields = [field.name for field in Layer._meta.fields]

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Layer.objects.filter(
            metadata__is_active=True
        )

        # filter by parent id
        pid = self.request.query_params.get("pid", None)
        self.queryset = view_helper.filter_queryset_service_pid(self.queryset, pid)

        # filter by query (title and abstract)
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_service_query(self.queryset, query)

        # filter by qorganization
        org = self.request.query_params.get("orgid", None)
        self.queryset = view_helper.filter_queryset_services_organization_id(self.queryset, org)

        # filter by uuid
        uuid = self.request.query_params.get("uuid", None)
        self.queryset = view_helper.filter_queryset_services_uuid(self.queryset, uuid)

        # order by
        order_by = self.request.query_params.get("order", LAYER_DEFAULT_ORDER)
        if order_by not in self.orderable_fields:
            order_by = LAYER_DEFAULT_ORDER
        self.queryset = view_helper.order_queryset(self.queryset, order_by)

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = LayerSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def retrieve(self, request, pk=None):
        try:
            tmp = Layer.objects.get(metadata__id=pk)
            if not tmp.metadata.is_active:
                return Response(status=423)
            return Response(LayerSerializer(tmp).data)
        except ObjectDoesNotExist:
            return Response(RESOURCE_NOT_FOUND, status=404)

    def update(self, request, pk=None):
        # Not supported
        pass

    def partial_update(self, request, pk=None):
        # Not supported
        pass

    def destroy(self, request, pk=None):
        # Not supported
        pass


class OrganizationViewSet(viewsets.ModelViewSet):
    """ Overview of all organizations matching the given parameters

        Query parameters:

            ag:     optional, filter for auto_generated organizations vs. real organizations
            order:  optional, orders by an attribute (e.g. id, email, default is organization_name)
            rpp:    optional, Number of results per page
    """
    serializer_class = OrganizationSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    permission_classes = (IsAuthenticated,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable_fields = [field.name for field in Organization._meta.fields]

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Organization.objects.all()

        # filter by real or auto generated organizations
        auto_generated = self.request.query_params.get("ag", None)
        auto_generated = utils.resolve_boolean_attribute_val(auto_generated)
        self.queryset = view_helper.filter_queryset_real_organization(self.queryset, auto_generated)

        # order by
        order_by = self.request.query_params.get("order", ORGANIZATION_DEFAULT_ORDER)
        if order_by not in self.orderable_fields:
            order_by = ORGANIZATION_DEFAULT_ORDER
        self.queryset = view_helper.order_queryset(self.queryset, order_by)

        return self.queryset


class MetadataViewSet(viewsets.GenericViewSet):
    """ Overview of all metadata matching the given parameters

        Query parameters:

            q:      optional, filters for the given query. Matches against title, abstract and keywords
            uuid:   optional, filters for the given uuid and returns only the matching element
            order:  optional, orders by an attribute (e.g. title, abstract, ..., default is hits)
            rpp:    optional, Number of results per page
    """
    serializer_class = MetadataSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    permission_classes = (IsAuthenticated,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable_fields = [field.name for field in Metadata._meta.fields]

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Metadata.objects.filter(
            is_active=True,
        )

        # filter by query
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_metadata_query(self.queryset, query)

        # filter by uuid
        uuid = self.request.query_params.get("uuid", None)
        self.queryset = view_helper.filter_queryset_metadata_uuid(self.queryset, uuid)

        # order by
        order_by = self.request.query_params.get("order", METADATA_DEFAULT_ORDER)
        if order_by not in self.orderable_fields:
            order_by = METADATA_DEFAULT_ORDER
        self.queryset = view_helper.order_queryset(self.queryset, order_by)

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = MetadataSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def retrieve(self, request, pk=None):
        try:
            tmp = Metadata.objects.get(id=pk)
            if not tmp.is_active:
                return Response(status=423)
            return Response(MetadataSerializer(tmp).data)
        except ObjectDoesNotExist:
            return Response(RESOURCE_NOT_FOUND, status=404)

    def update(self, request, pk=None):
        # Not supported
        pass

    def partial_update(self, request, pk=None):
        # Not supported
        pass

    def destroy(self, request, pk=None):
        # Not supported
        pass


class GroupViewSet(viewsets.GenericViewSet):
    """ Overview of all groups matching the given parameters

        Query parameters:

            orgid:  optional, filter for organizations
            order:  optional, orders by an attribute (e.g. id, organization, default is name)
            rpp:    optional, Number of results per page
    """
    serializer_class = GroupSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    permission_classes = (IsAuthenticated,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable_fields = [field.name for field in MrMapGroup._meta.fields]

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = MrMapGroup.objects.all()

        # filter by organization
        orgid = self.request.query_params.get("orgid", None)
        self.queryset = view_helper.filter_queryset_group_organization_id(self.queryset, orgid)

        # order by
        order_by = self.request.query_params.get("order", GROUP_DEFAULT_ORDER)
        if order_by not in self.orderable_fields:
            order_by = GROUP_DEFAULT_ORDER
        self.queryset = view_helper.order_queryset(self.queryset, order_by)

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = GroupSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def retrieve(self, request, pk=None):
        try:
            tmp = MrMapGroup.objects.get(id=pk)
            return Response(ServiceSerializer(tmp).data)
        except ObjectDoesNotExist:
            return Response(RESOURCE_NOT_FOUND, status=404)

    def update(self, request, pk=None):
        # Not supported
        pass

    def partial_update(self, request, pk=None):
        # Not supported
        pass

    def destroy(self, request, pk=None):
        # Not supported
        pass


class CatalogueViewSet(viewsets.GenericViewSet):
    """ Combines the serializers for a 'usual' catalogue api which provides most of the important information

        Query parameters:

            -----   REGULAR    -----
            q:                  optional, query
                                    * Type: str
                                    * multiple query arguments can be passed by using '+' like q=val1+val2
            type:               optional, specifies which type of resource shall be fetched
                                    * Type: str
                                    * Possible values are: ('service' | 'wms'| 'layer' | 'wfs' | 'feature' | 'dataset')
            cat:                optional, specifies a category id
                                    * Type: int
                                    * multiple ids can be passed by using '+' like cat=1+4
            cat-strict:         optional, specifies if multiple given categories shall be evaluated as OR or AND
                                    * Type: bool
                                    * if true, cat=1+4 returns only results that are in category 1 AND category 4
                                    * if false or not set, cat=1+4 returns results that are in category 1 OR category 4
            order:              optional, orders by an attribute
                                    * Type: str
                                    * e.g. 'title', 'identifier', ..., default is 'hits'
            rpp:                optional, number of results per page
                                    * Type: int

            -----   SPATIAL    -----
            bbox:               optional, specifies four coordinates which create a bounding box
                                    * Type: str
                                    * coordinates must be comma separated like 'x1,y1,x2,y2'
                                    * default srs for bbox coordinates is EPSG:4326
            bbox-srs:           optional, specifies a spatial reference system for the bbox
                                    * Type: str
                                    * If not set, the default 'EPSG:4326' is used
            bbox-strict:        optional, if true only results are returned, that are completely inside the bbox
                                    * Type: bool
                                    * If not set, overlapping results will be returned as well.

            -----   DIMENSION    -----
            time-min:           optional, specifies a date in ISO format (YYYY-mm-dd)
                                    * Type: str
                                    * only results with a time dimension on or after time-min will be returned
            time-max:           optional, specifies a date in ISO format (YYYY-mm-dd)
                                    * Type: str
                                    * only results with a time dimension on or before time-max will be returned
            elevation-unit:     optional, specifies a unit, that evaluates the evalution-min/-max parameters
                                    * Type: str
            elevation-min:      optional, specifies a numerical value
                                    * Type: float
                                    * only results with an elevation dimension larger or equal to elevation-min will be returned
            elevation-max:      optional, specifies a numerical value
                                    * Type: float
                                    * only results with an elevation dimension smaller or equal to elevation-min will be returned

    """
    serializer_class = CatalogueMetadataSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable_fields = [field.name for field in Metadata._meta.fields]

    def get_queryset(self):
        """ Fetch the base queryset

        Returns:
             The queryset
        """
        # Prefetches multiple related attributes to reduce the access time later!
        prefetches = [
            "keywords",
            "categories",
            "related_metadata",
            "related_metadata__metadata_to",
            "dimensions",
            "additional_urls",
            "contact",
            "licence",
            "featuretype__parent_service",
            "service__parent_service",
        ]
        only = [
            "id",
            "public_id",
            "identifier",
            "metadata_type",
            "title",
            "abstract",
            "bounding_geometry",
            "online_resource",
            "fees",
            "access_constraints",
            "licence",
            "service",
            "service__parent_service",
            "contact",
            "related_metadata",
            "categories",
            "dimensions",
            "keywords",
        ]

        self.queryset = Metadata.objects.filter(
            is_active=True,
        )
        self.queryset = self.queryset.only(
            *only
        ).prefetch_related(
            *prefetches
        )

        return self.queryset

    def filter_queryset(self, queryset):
        """ Filters the queryset

        Args:
            queryset (Queryset): Unfiltered queryset
        Returns:
             queryset (Queryset): Filtered queryset
        """
        # filter by dimensions
        time_min = self.request.query_params.get("time-min", None) or None
        time_max = self.request.query_params.get("time-max", None) or None
        elevation_unit = self.request.query_params.get("elevation-unit", None) or None
        elevation_min = self.request.query_params.get("elevation-min", None) or None
        elevation_max = self.request.query_params.get("elevation-max", None) or None
        queryset = view_helper.filter_queryset_metadata_dimension_time(queryset, time_min, time_max)
        queryset = view_helper.filter_queryset_metadata_dimension_elevation(
            queryset,
            elevation_min,
            elevation_max,
            elevation_unit
        )

        # filter by bbox extent. fully-inside and partially-inside are mutually exclusive
        bbox = self.request.query_params.get("bbox", None) or None
        bbox_srs = self.request.query_params.get("bbox-srs", DEFAULT_SRS_STRING)
        bbox_strict = utils.resolve_boolean_attribute_val(
            self.request.query_params.get("bbox-strict", False) or False
        )
        queryset = view_helper.filter_queryset_metadata_bbox(queryset, bbox, bbox_srs, bbox_strict)

        # filter by service type
        type = self.request.query_params.get("type", None)
        queryset = view_helper.filter_queryset_metadata_type(queryset, type)

        # filter by category
        category = self.request.query_params.get("cat", None)
        category_strict = utils.resolve_boolean_attribute_val(
            self.request.query_params.get("cat-strict", False) or False
        )
        queryset = view_helper.filter_queryset_metadata_category(queryset, category, category_strict)

        # filter by query
        query = self.request.query_params.get("q", None)
        q_test = self.request.query_params.get("q-test", False)
        queryset = view_helper.filter_queryset_metadata_query(queryset, query, q_test)

        # order by
        order_by = self.request.query_params.get("order", CATALOGUE_DEFAULT_ORDER)
        if order_by not in self.orderable_fields:
            order_by = CATALOGUE_DEFAULT_ORDER
        queryset = view_helper.order_queryset(queryset, order_by)

        return queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def list(self, request):
        qs = self.get_queryset()
        qs = self.filter_queryset(qs)
        tmp = self.paginate_queryset(qs)
        data = serialize_catalogue_metadata(tmp)
        resp = self.get_paginated_response(data)
        return resp

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    @resolve_metadata_public_id
    def retrieve(self, request, pk=None):
        try:
            tmp = Metadata.objects.get(id=pk)
            if not tmp.is_active:
                return Response(status=423)
            data = serialize_catalogue_metadata(tmp)
            return Response(data)
        except ObjectDoesNotExist:
            return Response(RESOURCE_NOT_FOUND, status=404)


class MonitoringViewSet(viewsets.ReadOnlyModelViewSet):
    """ Overview of the last Monitoring results

    """
    serializer_class = MonitoringSerializer

    def get_queryset(self):
        try:
            monitoring_run = MonitoringRun.objects.latest('start')
            monitorings = Monitoring.objects.filter(monitoring_run=monitoring_run)
        except ObjectDoesNotExist:
            return Monitoring.objects.all()
        return monitorings

    def retrieve(self, request, pk=None, *args, **kwargs):
        tmp = Monitoring.objects.filter(metadata=pk).order_by('-timestamp')

        if len(tmp) == 0:
            return Response(status=404)

        last_monitoring = tmp[0]
        sum_response = 0
        sum_availability = 0
        for monitor in tmp:
            sum_response += monitor.duration.microseconds
            if monitor.available:
                sum_availability += 1
        avg_response_microseconds = sum_response / len(tmp)
        avg_response_time = timezone.timedelta(microseconds=avg_response_microseconds)
        avg_availability = sum_availability / len(tmp) * 100
        result = {
            'last_monitoring': last_monitoring,
            'avg_response_time': avg_response_time,
            'avg_availability_percent': avg_availability
        }
        return Response(MonitoringSummarySerializer(result).data)


class SuggestionViewSet(viewsets.GenericViewSet):
    """ Returns suggestions based on the given input.

    Suggestions are currently created using the existing keywords and their relevance.

        Query parameters:

            -----   REGULAR    -----
            q:                  optional, query
                                    * Type: str
                                    * no multiple query arguments possible, only single
            max:                optional, max number of returned suggestions
                                    * Type: int
                                    * if not set, the default is 10

    """
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        # Prefilter search on database access to reduce amount of work
        query = self.request.query_params.get("q", None)
        filter = view_helper.create_keyword_query_filter(query)
        try:
            max_results = int(self.request.query_params.get("max", SUGGESTIONS_MAX_RESULTS))
        except ValueError:
            # Happens if non-numeric value has been given. Use fallback!
            max_results = SUGGESTIONS_MAX_RESULTS

        # Get matching keywords, count the number of relations to metadata records and order accordingly (most on top)
        self.queryset = Keyword.objects.filter(
            filter
        ).annotate(
            metadata_count=Count('metadata')
        ).order_by(
            '-metadata_count'
        )[:max_results]

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        data = {
            "suggestions":
                {
                    result.keyword: result.metadata_count for result in tmp
                }
        }
        data = OrderedDict(data)
        return self.get_paginated_response(data)


class CategoryViewSet(viewsets.GenericViewSet):
    """ Returns available categories and the number of related services.

        Query parameters:

            -----   REGULAR    -----
            q:                  optional, query
                                    * Type: str
                                    * no multiple query arguments possible, only single

    """
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination
    serializer_class = CategorySerializer

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        # Prefilter search on database access to reduce amount of work
        query = self.request.query_params.get("q", None)
        filter = view_helper.create_category_query_filter(query)

        # Get matching keywords, count the number of relations to metadata records and order accordingly (most on top)
        self.queryset = Category.objects.filter(
            filter
        ).annotate(
            metadata_count=Count('metadata')
        )

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME, key_prefix=API_CACHE_KEY_PREFIX))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = CategorySerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)
