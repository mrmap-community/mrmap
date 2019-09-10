# Create your views here.
from rest_framework import viewsets

from MapSkinner import utils
from api import view_helper
from api.serializers import ServiceSerializer, LayerSerializer, OrganizationSerializer, GroupSerializer, RoleSerializer
from service.models import Service, Layer
from structure.models import Organization, Group, Role


class ServiceViewSet(viewsets.ModelViewSet):
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
        queryset = Service.objects.all()

        # filter by service or service+layers
        las = self.request.query_params.get("las", False)
        las = not utils.resolve_boolean_attribute_val(las)
        queryset = queryset.filter(
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

        return queryset


class LayerViewSet(viewsets.ModelViewSet):
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
        auto_generated = self.request.query_params.get("ag", False)
        self.queryset = view_helper.filter_queryset_real_organization(self.queryset, auto_generated)

        return self.queryset


class GroupViewSet(viewsets.ModelViewSet):
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

