from django.db.models import Q

# Create your views here.
from rest_framework import viewsets

from MapSkinner import utils
from api.serializers import ServiceSerializer, LayerSerializer
from service.models import Service, Layer


class ServiceViewSet(viewsets.ModelViewSet):
    """ Overview of all services matching the given parameters

        Query parameters:

            type: optional, 'wms' or 'wfs'
            q: optional, search in abstract, title and keywords for a match
            org: optional, search for layers which are published by this organization (id)
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
        las = utils.resolve_boolean_attribute_val(las)
        las = not las
        queryset = queryset.filter(
            is_root=las
        )

        # filter by type
        service_type = self.request.query_params.get("type", None)
        if service_type is not None:
            queryset = queryset.filter(
                servicetype__name=service_type
            )

        # filter by query (title and abstract)
        query = self.request.query_params.get("q", None)
        if query is not None:
            # use Q for more complex OR usage
            queryset = queryset.filter(
                Q(metadata__title__icontains=query) |
                Q(metadata__abstract__icontains=query)
            )

        # filter by qorganization
        org = self.request.query_params.get("orgid", None)
        if org is not None:
            queryset = queryset.filter(
                metadata__contact_id=org
            )

        return queryset


class LayerViewSet(viewsets.ModelViewSet):
    """ Overview of all layers matching the given parameters

        Query parameters:

            pid: optional, refers to the parent service id
            q: optional, search in abstract, title and keywords for a match
            org: optional, search for layers which are published by this organization (id)
    """

    serializer_class = LayerSerializer

    def get_queryset(self):
        """ Specifies if the queryset shall be filtered or not

        Returns:
             The queryset
        """
        self.queryset = Layer.objects.all()

        # filter by parent id
        parent_id = self.request.query_params.get("pid", None)
        if parent_id is not None:
            self.queryset = self.queryset.filter(
                parent_service__id=parent_id
            )

        # filter by query (title and abstract)
        query = self.request.query_params.get("q", None)
        if query is not None:
            self.queryset = self.queryset.filter(
                Q(metadata__title__icontains=query) |
                Q(metadata__abstract__icontains=query) |
                Q(metadata__keywords__keyword=query)
            )

        # filter by qorganization
        org = self.request.query_params.get("orgid", None)
        if org is not None:
            self.queryset = self.queryset.filter(
                metadata__contact_id=org
            )
        return self.queryset
