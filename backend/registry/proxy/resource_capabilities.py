"""Read only capabilities documents of a single registered layer or feature type.

The security proxy of a service (registry/proxy/mixins.py) answers the capabilities
of the whole service. The views in this module answer the same document, but
advertising only one layer or one feature type, so that a viewer can be pointed to
exactly one resource of a service (see registry/helper/resource_capabilities.py).

The urls of these documents are the stable adresses of a registered resource:

    /mrmap-proxy/wms/<uuid of the service>/layer/<uuid of the layer>
    /mrmap-proxy/wfs/<uuid of the service>/featuretype/<uuid of the feature type>

The path of the url names service and resource, therefore the query parameters of a
capabilities request are answered from the path and the url needs none. A client
which appends SERVICE, REQUEST and VERSION like any OGC client does gets the same
document, after the appended version was checked against the service.

Nothing of these documents is stored. They are generated for every request out of
the registry, so an update job which changed the service changes this document with
the next request, and the answer is asked not to be cached by anyone.
"""
from functools import cached_property

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from registry.helper.resource_capabilities import (AMBIGUOUS_ELEMENT, MALFORMED,
                                                   NO_SUCH_ELEMENT,
                                                   NOT_SUPPORTED, CapabilitiesError,
                                                   service_element_capabilities)
from registry.ows_lib.response.exceptions import \
    NotImplementedError as MrMapNotImplementedError
from registry.ows_lib.response.exceptions import \
    RuntimeError as OGCRuntimeError
from registry.ows_lib.response.exceptions import (
    InvalidParameterValueException, LayerNotDefined)
from registry.proxy.wfs_proxy import WebFeatureServiceProxy
from registry.proxy.wms_proxy import WebMapServiceProxy


class ServiceElementCapabilitiesMixin:
    """Answers the capabilities of the service of the proxy narrowed to one resource.

    Mixed in before the proxy view of a service, so it replaces only the answer of
    GetCapabilities of that proxy and inherits everything the proxy needs to find and
    secure "service": authentication, the security information of the service and the
    urls the document is answered with.

    Attributes:
        element_relation (str): the name of the relation of the service model which
            holds the resources of the service, "layers" or "featuretypes".
        element_pk_kwarg (str): the name of the path converter of the resource.
        element_name (str): how the resource is called in an exception report.
        element_not_defined (class): the OGC exception which answers a resource the
            service does not advertise.
    """

    element_relation = None
    element_pk_kwarg = None
    element_name = "element"
    element_not_defined = OGCRuntimeError

    @cached_property
    def element(self):
        """The :class:`registry.models.service.ServiceElement` the url points to.

        The resource is read over the relation of the service the proxy found, so a
        resource of another service and a resource which does not exist at all are
        answered in the same way.
        """
        try:
            return getattr(self.service, self.element_relation).get(
                pk=self.kwargs[self.element_pk_kwarg])
        except ObjectDoesNotExist:
            raise CapabilitiesError(
                NO_SUCH_ELEMENT,
                f"The service does not have a registered {self.element_name} with "
                f"the identifier '{self.kwargs[self.element_pk_kwarg]}'.",
                status=404,
            )

    def initialize_request(self, request, *args, **kwargs):
        """Add the parameters of a capabilities request which the url path already names.

        SERVICE, REQUEST and VERSION identify a capabilities request in an OGC url,
        but they are not part of the url of a single resource: the path says which
        service and which resource is asked for. They are added as far as the client
        did not append them itself, so that the proxy is handed a capabilities
        request, and the version of a client which does append one is still
        negotiated the way the proxy negotiates versions.

        The parameters are added to the request of the framework before it is
        wrapped, because the proxy reads the OGC parameters out of the wrapped
        request in ``initial()`` and the wrapper keeps the parameters it saw first.
        """
        params = request.GET.copy()
        given = {key.upper() for key in params.keys()}
        defaults = {
            "SERVICE": self.service_type,
            "REQUEST": "GetCapabilities",
            "VERSION": self.service_version,
        }
        added = {
            name: value for name, value in defaults.items() if name not in given
        }
        for name, value in added.items():
            params[name] = value
        if added:
            request.GET = params
            # the query string of the url is answered to the client and used to
            # build the urls of the document, so it names the same parameters
            request.META["QUERY_STRING"] = params.urlencode(safe="/:")
        return super().initialize_request(request, *args, **kwargs)

    def get_capabilities(self):
        """The capabilities of the service, advertising only the requested resource."""
        try:
            document = service_element_capabilities(
                service=self.service, element=self.element, request=self.request
            )
        except CapabilitiesError as error:
            return self.element_capabilities_exception(error)
        return HttpResponse(
            content=document,
            content_type="application/xml",
            headers={"Cache-Control": "no-store"},
        )

    def element_capabilities_exception(self, error: CapabilitiesError):
        """The exception report for a document which can not be narrowed down."""
        if error.code == NO_SUCH_ELEMENT:
            exception = self.element_not_defined
        elif error.code == NOT_SUPPORTED:
            exception = MrMapNotImplementedError
        elif error.code in (AMBIGUOUS_ELEMENT, MALFORMED):
            exception = OGCRuntimeError
        else:
            exception = OGCRuntimeError
        return exception(
            service_type=self.service_type,
            service_version=self.ogc_request.service_version,
            message=str(error),
            status=error.status,
        )


class WebMapServiceLayerCapabilities(ServiceElementCapabilitiesMixin, WebMapServiceProxy):
    """The capabilities of a registered WMS, advertising only one of its layers."""

    element_relation = "layers"
    element_pk_kwarg = "layer_pk"
    element_name = "layer"
    element_not_defined = LayerNotDefined


class WebFeatureServiceFeatureTypeCapabilities(ServiceElementCapabilitiesMixin,
                                               WebFeatureServiceProxy):
    """The capabilities of a registered WFS, advertising only one of its feature types."""

    element_relation = "featuretypes"
    element_pk_kwarg = "featuretype_pk"
    element_name = "feature type"
    element_not_defined = InvalidParameterValueException
