# Create your views here.
from rest_framework import viewsets, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from MapSkinner import utils
from api import view_helper
from api.serializers import ServiceSerializer, LayerSerializer, OrganizationSerializer, GroupSerializer, RoleSerializer, \
    MetadataSerializer
from service.models import Service, Layer, Metadata
from structure.models import Organization, Group, Role


class ServiceViewSet(viewsets.GenericViewSet):
    """ Overview of all services matching the given parameters

        Query parameters:

            type: optional, 'wms' or 'wfs'
            q: optional, search in abstract, title and keywords for a match
            orgid: optional, search for layers which are published by this organization (id)
            las: (layer-as-service) optional, returns services and layers all in one

    """
    serializer_class = ServiceSerializer

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Service.objects.all()

        # filter by service or service+layers
        las = self.request.query_params.get("las", False)
        las = not utils.resolve_boolean_attribute_val(las)
        self.queryset = self.queryset.filter(
            is_root=las
        )

        # filter by type
        service_type = self.request.query_params.get("type", None)
        self.queryset = view_helper.filter_queryset_service_type(self.queryset, service_type)

        # filter by query (title and abstract)
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_service_query(self.queryset, query)

        # filter by qorganization
        org = self.request.query_params.get("orgid", None)
        self.queryset = view_helper.filter_queryset_services_organization_id(self.queryset, org)

        return self.queryset

    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
        serializer = ServiceSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    def retrieve(self, request, pk=None):
        tmp = Service.objects.get(id=pk)
        return Response(ServiceSerializer(tmp).data)

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

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Layer.objects.all()

        # filter by parent id
        pid = self.request.query_params.get("pid", None)
        self.queryset = view_helper.filter_queryset_service_pid(self.queryset, pid)

        # filter by query (title and abstract)
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_service_query(self.queryset, query)

        # filter by qorganization
        org = self.request.query_params.get("orgid", None)
        self.queryset = view_helper.filter_queryset_services_organization_id(self.queryset, org)

        return self.queryset

    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
        serializer = LayerSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    def retrieve(self, request, pk=None):
        tmp = Layer.objects.get(id=pk)
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
    """ Overview of all organizations matching the given parameters

        Query parameters:

            ag: (auto generated) optional, filter for auto_generated organizations vs. real organizations
    """
    serializer_class = MetadataSerializer

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Metadata.objects.all()

        # filter by query
        query = self.request.query_params.get("q", None)
        self.queryset = view_helper.filter_queryset_metadata_query(self.queryset, query)

        return self.queryset

    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
        serializer = MetadataSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

    def retrieve(self, request, pk=None):
        tmp = Metadata.objects.get(id=pk)
        return Response(MetadataSerializer(tmp).data)

    def update(self, request, pk=None):
        pass

    def partial_update(self, request, pk=None):
        pass

    def destroy(self, request, pk=None):
        pass


class GroupViewSet(viewsets.GenericViewSet):
    """ Overview of all organizations matching the given parameters

        Query parameters:

            orgid: optional, filter for organizations
    """
    serializer_class = GroupSerializer

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

    def list(self, request):
        tmp = self.paginate_queryset(self.queryset)
        serializer = GroupSerializer(tmp, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        pass

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
    """ Overview of all organizations matching the given parameters

        Query parameters:

            ag: (auto generated) optional, filter for auto_generated organizations vs.
    """
    serializer_class = RoleSerializer

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Role.objects.all()

        return self.queryset

