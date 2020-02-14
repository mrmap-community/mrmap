# Create your views here.
from datetime import timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from MapSkinner import utils
from api import view_helper
from api.serializers import ServiceSerializer, LayerSerializer, OrganizationSerializer, GroupSerializer, RoleSerializer, \
    MetadataSerializer, CatalogueMetadataSerializer, MonitoringSerializer, MonitoringSummarySerializer
from api.settings import API_CACHE_TIME, API_ALLOWED_HTTP_METHODS
from service.models import Service, Layer, Metadata
from structure.models import Organization, Group, Role
from monitoring.models import Monitoring, MonitoringRun


class APIPagination(PageNumberPagination):
    """ Pagination class for this API

    Overwrites the default PageNumberPagination such that the following GET parameters can be used to
    modify the pagination style:

        rpp (int): Number of results per page

    """
    page_size_query_param = "rpp"


class ServiceViewSet(viewsets.GenericViewSet):
    """ Overview of all services matching the given parameters

        Query parameters:

            type: optional, 'wms' or 'wfs'
            q: optional, search in abstract, title and keywords for a match
            orgid: optional, search for layers which are published by this organization (id)
            las: (layer-as-service) optional, returns services and layers all in one

    """
    serializer_class = ServiceSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Service.objects.filter(
            metadata__is_active=True,
            is_root=True
        )

        # filter by service or service+layers
        las = self.request.query_params.get("las", False)
        las = utils.resolve_boolean_attribute_val(las)
        if las:
            self.queryset = self.queryset.filter(
                Q(is_root=las) |
                Q(is_root=not las)
            )

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

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
        serializer = ServiceSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        try:
            tmp = Layer.objects.get(id=pk)
            if not tmp.metadata.is_active:
                return Response(status=423)
            serializer = LayerSerializer(tmp)
        except ObjectDoesNotExist:
            tmp = Service.objects.get(id=pk)
            if not tmp.metadata.is_active:
                return Response(status=423)
            serializer = ServiceSerializer(tmp)

        return Response(serializer.data)

    def update(self, request, pk=None):
        pass

    def partial_update(self, request, pk=None):
        pass

    def destroy(self, request, pk=None):
        pass


class LayerViewSet(viewsets.GenericViewSet):
    """ Overview of all layers matching the given parameters

        Query parameters:
            pid: optional, refers to the parent service id
            q: optional, search in abstract, title and keywords for a match
            orgid: optional, search for layers which are published by this organization (id)
    """

    serializer_class = LayerSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

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

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
        serializer = LayerSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        tmp = Layer.objects.get(id=pk)
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

            ag: (auto generated) optional, filter for auto_generated organizations vs. real organizations
    """
    serializer_class = OrganizationSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

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

        return self.queryset


class MetadataViewSet(viewsets.GenericViewSet):
    """ Overview of all metadata matching the given parameters

        Query parameters:

            q: optional, filters for the given query. Matches against title, abstract and keywords
            uuid: optional, filters for the given uuid and returns only the matching element
    """
    serializer_class = MetadataSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

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

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
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

            orgid: optional, filter for organizations
    """
    serializer_class = GroupSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Group.objects.all()

        # filter by organization
        orgid = self.request.query_params.get("orgid", None)
        self.queryset = view_helper.filter_queryset_group_organization_id(self.queryset, orgid)

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
        serializer = GroupSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def retrieve(self, request, pk=None):
        tmp = Group.objects.get(id=pk)
        return Response(ServiceSerializer(tmp).data)

    def update(self, request, pk=None):
        pass

    def partial_update(self, request, pk=None):
        pass

    def destroy(self, request, pk=None):
        pass


class RoleViewSet(viewsets.ModelViewSet):
    """ Overview of all roles

    """
    serializer_class = RoleSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Role.objects.all()

        return self.queryset


class CatalogueViewSet(viewsets.GenericViewSet):
    """ Combines the serializers for a 'usual' catalogue api which provides most of the important information

        Query parameters:

            q: optional, query
            type: optional, specifies which type of resource shall be fetched ('wms' or 'wfs')
    """
    serializer_class = CatalogueMetadataSerializer
    http_method_names = API_ALLOWED_HTTP_METHODS
    pagination_class = APIPagination


    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Metadata.objects.filter(
            is_active=True,
        )

        # filter by service type
        type = self.request.query_params.get("type", None)
        self.queryset = view_helper.filter_queryset_metadata_service_type(self.queryset, type)

        # filter by query
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_metadata_query(self.queryset, query)

        return self.queryset

    # https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
    # Cache requested url for time t
    @method_decorator(cache_page(API_CACHE_TIME))
    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
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


class MonitoringViewSet(viewsets.ReadOnlyModelViewSet):
    """ Overview of the last Monitoring results

    """
    serializer_class = MonitoringSerializer

    def get_queryset(self):
        monitoring_run = MonitoringRun.objects.latest('start')
        monitorings = Monitoring.objects.filter(monitoring_run=monitoring_run)
        return monitorings

    def retrieve(self, request, pk=None, *args, **kwargs):
        tmp = Monitoring.objects.filter(metadata=pk).order_by('-timestamp')
        last_monitoring = tmp[0]
        sum_response = 0
        sum_availability = 0
        for monitor in tmp:
            sum_response += monitor.duration.microseconds
            if monitor.available:
                sum_availability += 1
        avg_response_microseconds = sum_response / len(tmp)
        avg_response_time = timedelta(microseconds=avg_response_microseconds)
        avg_availability = sum_availability / len(tmp) * 100
        result = {
            'last_monitoring': last_monitoring,
            'avg_response_time': avg_response_time,
            'avg_availability_percent': avg_availability
        }
        return Response(MonitoringSummarySerializer(result).data)
