"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""

from monitoring.helper.urlHelper import UrlHelper
from resourceNew.enums.service import OGCOperationEnum, OGCServiceEnum, OGCServiceVersionEnum


class WfsHelper:

    def __init__(self, service):
        self.service = service
        self.parent_service = service if service.metadata.is_root() else service.parent_service
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
        uri = self.parent_service.operation_urls.filter(
            operation=OGCOperationEnum.GET_CAPABILITIES.value,
            method="Get"
        )
        uri = uri.first()
        if uri is None:
            return
        uri = uri.url
        request_type = OGCOperationEnum.GET_CAPABILITIES.value
        service_version = self.parent_service.service_type.version
        service_type = OGCServiceEnum.WFS.value

        queries = [
            ('REQUEST', request_type),
            ('VERSION', service_version),
            ('SERVICE', service_type)
        ]
        url = UrlHelper.build(uri, queries)
        return url

    def get_list_stored_queries(self):
        """ Creates the url for the wfs ListStoredQueries request.

        Returns:
            str: URL for ListStoredQueries request.
        """
        uri = self.service.operation_urls.filter(
            operation=OGCOperationEnum.LIST_STORED_QUERIES.value,
            method="Get"
        ).first()
        if uri is None:
            return
        uri = uri.url
        request_type = OGCOperationEnum.LIST_STORED_QUERIES.value
        service_version = self.service.service_type.version
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
            uri = self.parent_service.operation_urls.filter(
                operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE,
                method="Get"
            ).first()
        except AttributeError:
            pass
        if uri is None:
            return
        if type_name is None:
            return
        uri = uri.url
        request_type = OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value
        service_version = self.parent_service.service_type.version
        service_type = OGCServiceEnum.WFS.value

        if service_version == OGCServiceVersionEnum.V_1_0_0.value \
                or service_version == OGCServiceVersionEnum.V_1_1_0.value:
            queries = [
                ('REQUEST', request_type),
                ('VERSION', service_version),
                ('SERVICE', service_type),
                ('typeName', type_name)
            ]
        else:
            queries = [
                ('REQUEST', request_type),
                ('VERSION', service_version),
                ('SERVICE', service_type),
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
            uri = self.parent_service.operation_urls.filter(
                operation=OGCOperationEnum.GET_FEATURE.value,
                method="Get"
            ).first()
        except AttributeError:
            pass

        if uri is None:
            return
        if type_name is None:
            return

        uri = uri.url
        request_type = OGCOperationEnum.GET_FEATURE.value
        service_version = self.parent_service.service_type.version
        service_type = OGCServiceEnum.WFS.value

        if service_version == OGCServiceVersionEnum.V_1_0_0.value \
                or service_version == OGCServiceVersionEnum.V_1_1_0.value:
            queries = [
                ('REQUEST', request_type),
                ('VERSION', service_version),
                ('SERVICE', service_type),
                ('typeName', type_name),
                ('MAXFEATURES', 1)
            ]
        else:
            queries = [
                ('REQUEST', request_type),
                ('VERSION', service_version),
                ('SERVICE', service_type),
                ('typeNames', type_name),
                ('COUNT', 1)
            ]

        url = UrlHelper.build(uri, queries)
        return url
