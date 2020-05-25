"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""

from service.models import Service
from service.helper.enums import OGCOperationEnum, OGCServiceEnum, OGCServiceVersionEnum
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

    def set_2_0_2_urls(self):
        """ Sets the urls for the wfs 2.0.2 version."""
        self.list_stored_queries = self.get_list_stored_queries()

    def get_get_capabilities_url(self):
        """ Creates the url for the wfs GetCapabilities request.

        Returns:
            str: URL for GetCapabilities request.
        """
        uri = self.service.get_capabilities_uri_GET
        if uri is None:
            return
        request_type = OGCOperationEnum.GET_CAPABILITIES.value
        service_version = self.service.servicetype.version
        service_type = OGCServiceEnum.WFS.value

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
        request_type = OGCOperationEnum.LIST_STORED_QUERIES.value
        service_version = self.service.servicetype.version
        service_type = OGCServiceEnum.WFS.value

        queries = [('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type)]
        url = UrlHelper.build(uri, queries)
        return url

    def get_describe_featuretype_url(self, type_name: str):
        """ Creates the url for the wfs DescribeFeatureType request.

        Args:
            type_name (str): The name of the feature type to check.
        Returns:
            str: URL for DescribeFeatureType request.
        """
        uri = None
        try:
            uri = self.service.describe_featuretype_uri_GET
        except AttributeError:
            # TODO:
            #   self.service.describe_featuretype_uri_GET is not implemented yet.
            #   We can remove the try catch block as soon as this was done.
            pass
        if uri is None:
            return
        if type_name is None:
            return
        request_type = OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value
        service_version = self.service.servicetype.version
        service_type = OGCServiceEnum.WFS.value

        queries = None
        if service_version == OGCServiceVersionEnum.V_1_0_0.value:
            queries = [
                ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type),
                ('typeName', type_name)
            ]
        elif service_version == OGCServiceVersionEnum.V_1_1_0.value:
            queries = [
                ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type),
                ('typeName', type_name)
            ]
        else:
            queries = [
                ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type),
                ('typeNames', type_name)
            ]

        url = UrlHelper.build(uri, queries)
        return url

    def get_get_feature_url(self, type_name: str):
        """ Creates the url for the wfs getFeature request.

        Args:
            type_name (str): The name of the feature type to check.
        Returns:
            str: URL for getFeature request.
        """
        uri = None
        try:
            uri = self.service.get_feature_uri_GET
        except AttributeError:
            # TODO:
            #   self.service.get_feature_uri_GET is not implemented yet.
            #   We can remove the try catch block as soon as this was done.
            pass

        if uri is None:
            return
        if type_name is None:
            return

        request_type = OGCOperationEnum.GET_FEATURE.value
        service_version = self.service.servicetype.version
        service_type = OGCServiceEnum.WFS.value

        queries = None
        if service_version == OGCServiceVersionEnum.V_1_0_0.value:
            queries = [
                ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type),
                ('typeName', type_name), ('MAXFEATURES', 1)
            ]
        elif service_version == OGCServiceVersionEnum.V_1_1_0.value:
            queries = [
                ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type),
                ('typeName', type_name), ('MAXFEATURES', 1)
            ]
        else:
            queries = [
                ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type),
                ('typeNames', type_name), ('COUNT', 1)
            ]

        url = UrlHelper.build(uri, queries)
        return url
