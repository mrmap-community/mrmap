from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from extras.viewsets import NestedViewSetMixin
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.querys.alerts import (is_visible, registered_services,
                                    service_alerts)
from registry.serializers.alerts import ServiceAlertSerializer
from rest_framework import mixins
from rest_framework.exceptions import NotFound
from rest_framework.viewsets import GenericViewSet
from rest_framework_json_api.filters import QueryParameterValidationFilter


class ServiceAlertListView(NestedViewSetMixin, mixins.ListModelMixin,
                           GenericViewSet):
    """ Endpoint answers the states of one service which need attention

        list:
            Retrieves what an administrator has to do about the service: the
            state of its last monitoring run, of its last update job and of the
            schedules it did not keep - and of a catalogue also the records its
            last harvesting job left behind.

    Nothing of this is stored: the answered alerts are derived from the runs and
    jobs of the service, which means that an alert disappears as soon as the
    state behind it is fixed. A service answers at most one alert per category,
    so the alerts of a service are a short list, answered with the worst first.

    Like the other read only endpoints of the registry api this endpoint is
    answered for every client, but the alerts are only answered for a service
    which the user which asks may see.
    """
    serializer_class = ServiceAlertSerializer
    # no queryset is narrowed down here, but the query parameters of a client
    # are still validated against the rules of the api
    filter_backends = [QueryParameterValidationFilter]
    http_method_names = ["get", "head", "options"]

    #: the model of the kind of service whose alerts this endpoint answers
    service_model = None

    def get_queryset(self):
        """The alerts of the service the request addresses.

        Returns:
            list: the alerts to attend to, worst first

        Raises:
            NotFound: if the addressed service is not registered, is the
                candidate of an update or is not visible to the user which asks
            Http404: if the path of the request names an id which no service of
                this kind can have
        """
        try:
            service = get_object_or_404(
                registered_services(self.service_model),
                pk=self.get_parents_query_dict().get('service'))
        except (ValueError, ValidationError):
            # the id of the path can not belong to a service of this kind, which
            # is answered like an id which no service of this kind has
            raise Http404
        if not is_visible(service, self.request.user):
            # the alerts of a service would tell about a service which is not
            # visible to the user, so the answer stays the same as for a service
            # which is not registered at all
            raise NotFound(_(
                "The service of this request is not visible to you."))
        return service_alerts(service)


class WebMapServiceAlertListView(ServiceAlertListView):
    """ Endpoint answers the states of a map service which need attention

        list:
            Retrieves what an administrator has to do about the map service
    """
    service_model = WebMapService


class WebFeatureServiceAlertListView(ServiceAlertListView):
    """ Endpoint answers the states of a feature service which need attention

        list:
            Retrieves what an administrator has to do about the feature service
    """
    service_model = WebFeatureService


class CatalogueServiceAlertListView(ServiceAlertListView):
    """ Endpoint answers the states of a catalogue which need attention

        list:
            Retrieves what an administrator has to do about the catalogue, which
            includes the records its last harvesting job left behind
    """
    service_model = CatalogueService
