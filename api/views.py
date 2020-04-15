# Create your views here.
from celery.result import AsyncResult
from django.core.exceptions import ObjectDoesNotExist
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

from MapSkinner import utils
from MapSkinner.decorator import check_permission
from MapSkinner.messages import SERVICE_NOT_FOUND, PARAMETER_ERROR, \
    RESOURCE_NOT_FOUND, SERVICE_REMOVED
from MapSkinner.responses import DefaultContext, APIResponse
from api import view_helper
from api.forms import TokenForm
from api.permissions import CanRegisterService, CanRemoveService, CanActivateService

from api.serializers import ServiceSerializer, LayerSerializer, OrganizationSerializer, GroupSerializer, RoleSerializer, \
    MetadataSerializer, CatalogueMetadataSerializer, PendingTaskSerializer
from api.settings import API_CACHE_TIME, API_ALLOWED_HTTP_METHODS, CATALOGUE_DEFAULT_ORDER, SERVICE_DEFAULT_ORDER, \
    LAYER_DEFAULT_ORDER, ORGANIZATION_DEFAULT_ORDER, METADATA_DEFAULT_ORDER, GROUP_DEFAULT_ORDER
from service import tasks
from service.helper import service_helper
from service.models import Service, Layer, Metadata
from structure.models import Organization, MrMapGroup, Permission, PendingTask
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
    Permission(
        can_generate_api_token=True
    )
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
    @method_decorator(cache_page(API_CACHE_TIME))
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
        user = user_helper.get_user(request)
        params = {
            "user": user
        }
        params.update(request.POST.dict())
        pending_task = service_serializer.create(validated_data=params)

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
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        try:
            tmp = Layer.objects.get(metadata__id=pk)
            if not tmp.metadata.is_active:
                return Response(status=423)
            serializer = LayerSerializer(tmp)
        except ObjectDoesNotExist:
            tmp = Service.objects.get(metadata__id=pk)
            if not tmp.metadata.is_active:
                return Response(status=423)
            serializer = ServiceSerializer(tmp)

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
        pass

    def partial_update(self, request, pk=None):
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
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = LayerSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        tmp = Layer.objects.get(metadata__id=pk)
        if not tmp.metadata.is_active:
            return Response(status=423)
        return Response(LayerSerializer(tmp).data)

    def update(self, request, pk=None):
        pass

    def partial_update(self, request, pk=None):
        pass

    def destroy(self, request, pk=None):
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
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = MetadataSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        tmp = Metadata.objects.get(id=pk)
        if not tmp.is_active:
            return Response(status=423)
        return Response(MetadataSerializer(tmp).data)

    def update(self, request, pk=None):
        pass

    def partial_update(self, request, pk=None):
        pass

    def destroy(self, request, pk=None):
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
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = GroupSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        tmp = MrMapGroup.objects.get(id=pk)
        return Response(ServiceSerializer(tmp).data)

    def update(self, request, pk=None):
        pass

    def partial_update(self, request, pk=None):
        pass

    def destroy(self, request, pk=None):
        pass


class CatalogueViewSet(viewsets.GenericViewSet):
    """ Combines the serializers for a 'usual' catalogue api which provides most of the important information

        Query parameters:

            -----   REGULAR    -----
            q:      optional, query (multiple query arguments can be passed by using '+' like q=val1+val2)
            type:   optional, specifies which type of resource shall be fetched ('wms'| 'wfs' | 'dataset')
            order:  optional, orders by an attribute (e.g. title, identifier, default is hits)
            rpp:    optional, Number of results per page

            -----   SPATIAL    -----
            bbox-srs:           optional, specifies another spatial reference system for the parameter `fully-inside` and `partially-inside`. If not given, the default is EPSG:4326
            fully-inside:       optional, specifies four coordinates, that span a bbox. Only results fully inside this bbox will be returned
            partially-inside:   optional, specifies four coordinates, that span a bbox. Only results fully or partially inside this bbox will be returned

    """
    serializer_class = CatalogueMetadataSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

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

        # filter by bbox extent. fully-inside and partially-inside are mutually exclusive
        fully_inside = self.request.query_params.get("fully-inside", None)
        part_inside = self.request.query_params.get("partially-inside", None)
        bbox_srs = self.request.query_params.get("bbox-srs", "EPSG:4326")

        is_full = fully_inside is not None and part_inside is None
        is_intersected = fully_inside is None and part_inside is not None
        bbox = fully_inside or part_inside
        if fully_inside is not None and part_inside is not None:
            raise Exception("Parameter fully-inside and part-inside can not be in the same request.")
        elif is_full:
            self.queryset = view_helper.filter_queryset_metadata_inside_bbox(self.queryset, bbox, bbox_srs)
        elif is_intersected:
            self.queryset = view_helper.filter_queryset_metadata_intersects_bbox(self.queryset, bbox, bbox_srs)

        # filter by service type
        type = self.request.query_params.get("type", None)
        self.queryset = view_helper.filter_queryset_metadata_type(self.queryset, type)

        # filter by query
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_metadata_query(self.queryset, query)

        # order by
        order_by = self.request.query_params.get("order", CATALOGUE_DEFAULT_ORDER)
        if order_by not in self.orderable_fields:
            order_by = CATALOGUE_DEFAULT_ORDER
        self.queryset = view_helper.order_queryset(self.queryset, order_by)

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    #@method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.get_queryset())
        serializer = CatalogueMetadataSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        tmp = Metadata.objects.get(id=pk)
        if not tmp.is_active:
            return Response(status=423)
        return Response(CatalogueMetadataSerializer(tmp).data)
