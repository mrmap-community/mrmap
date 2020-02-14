from service.models import Service
from service.helper.enums import ServiceOperationEnum, ServiceEnum
from monitoring.helper.urlHelper import UrlHelper


class WfsHelper:

    def __init__(self, service: Service):
        self.service = service
        self.get_capabilities_url = self.get_get_capabilities_url()
        self.list_stored_queries = None

    def set_1_1_0_urls(self):
        """ Sets the urls for the wfs 1.1.0 version."""
        pass

    def set_2_0_0_urls(self):
        """ Sets the urls for the wfs 2.0.0 version."""
        self.list_stored_queries = self.get_list_stored_queries()

    def get_get_capabilities_url(self):
        """ Creates the url for the wfs GetCapabilities request.

        Returns:
            str: URL for GetCapabilities request.
        """
        uri = self.service.get_capabilities_uri_GET
        if uri is None:
            return
        request_type = ServiceOperationEnum.GET_CAPABILITIES.value
        service_version = self.service.servicetype.version
        service_type = ServiceEnum.WFS.value

        queries = [('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type)]
        url = UrlHelper.build(uri, queries)
        return url

    def get_list_stored_queries(self):
        """ Creates the url for the wfs ListStoredQueries request.

        Returns:
            str: URL for ListStoredQueries request.
        """
        uri = self.service.list_stored_queries_uri_GET
        if uri is None:
            return
        request_type = ServiceOperationEnum.LIST_STORED_QUERIES.value
        service_version = self.service.servicetype.version
        service_type = ServiceEnum.WFS.value

        queries = [('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type)]
        url = UrlHelper.build(uri, queries)
        return url
