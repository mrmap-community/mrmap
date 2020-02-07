"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 09.12.2019

"""
from datetime import timedelta
import difflib

from service.helper.crypto_handler import CryptoHandler
from monitoring.models import MonitoringResult
from service.helper.common_connector import CommonConnector
from service.helper.xml_helper import parse_xml
from service.models import Metadata, Document
from service.helper.enums import ServiceEnum, MetadataEnum, ServiceOperationEnum, VersionEnum


class Monitor:

    def __init__(self, metadata: Metadata = None):
        self.metadata = metadata

    class ServiceStatus:
        """ Holds all required information about the service status.

        Attributes:
            success (bool): Success of the status. Holds True if service received a success status, False otherwise.
            status (int): The actual response status of the service.
            message (str): The response text of the request.
            duration (timedelta): The duration of the request.
        """
        def __init__(self, success: bool, message: str, status: int = None, duration: timedelta = None):
            self.success = success
            self.status = status
            self.message = message
            self.duration = duration

    def run_checks(self):
        """ Run checks for all ogc operations.

        Returns:
            nothing
        """
        service_type = self.metadata.service.servicetype.name.lower()
        metadata_type = self.metadata.metadata_type.type.lower()
        if metadata_type == MetadataEnum.LAYER.value.lower():
            if service_type.lower() == ServiceEnum.WMS.value.lower():
                get_map_url = self.get_map_url()
                if get_map_url is not None:
                    self.check_service(get_map_url)
                get_feature_info_url = self.get_feature_info_url()
                if get_feature_info_url is not None:
                    self.check_service(get_feature_info_url)
            # TODO add get_legend_graphic
            # TODO get_styles
            pass
        elif metadata_type == MetadataEnum.SERVICE.value.lower():
            if (service_type.lower() == ServiceEnum.WMS.value.lower())\
                    or (service_type.lower() == ServiceEnum.WFS.value.lower()):
                get_capabilities_url = self.get_capabilities_url()
                if get_capabilities_url is not None:
                    self.check_service(get_capabilities_url)

    def get_feature_info_url(self):
        """ Creates the url for the wms getFeatureInfo request.

        Returns:
            str: URL for getFeatureInfo request.
        """
        service = self.metadata.service
        uri = service.get_feature_info_uri_GET
        if uri is None:
            return
        request_type = ServiceOperationEnum.GET_FEATURE_INFO.value
        service_version = service.servicetype.version
        layers = service.layer.identifier
        styles = ''
        crs = f'EPSG:{service.layer.bbox_lat_lon.crs.srid}'
        bbox = ','.join(map(str, service.layer.bbox_lat_lon.extent))
        width = 0
        height = 0
        query_layers = layers
        x = 0
        y = 0
        url = (
            f'{uri}REQUEST={request_type}&VERSION={service_version}&LAYERS={layers}&STYLES={styles}&CRS={crs}'
            f'&BBOX={bbox}&WIDTH={width}&HEIGHT={height}&QUERY_LAYERS={query_layers}'
        )
        if service_version.lower() == VersionEnum.V_1_3_0.value.lower():
            url = f'{url}&I={x}&J={y}'
        else:
            url = f'{url}&X={x}&Y={y}'
        return url

    def get_map_url(self):
        """ Creates the url for the wms getMap request.

        Returns:
            str: URL for getMap request.
        """
        service = self.metadata.service
        uri = service.get_map_uri_GET
        if uri is None:
            return
        request_type = ServiceOperationEnum.GET_MAP.value
        service_version = service.servicetype.version
        layers = service.layer.identifier
        crs = f'EPSG:{service.layer.bbox_lat_lon.crs.srid}'
        bbox = ','.join(map(str, service.layer.bbox_lat_lon.extent))
        styles = ''
        width = 1
        height = 1
        service_format = str(service.formats.all()[0])
        if 'image/png' in [str(f) for f in service.formats.all()]:
            service_format = 'image/png'
        url = (
            f'{uri}REQUEST={request_type}&VERSION={service_version}&LAYERS={layers}&CRS={crs}'
            f'&BBOX={bbox}&STYLES={styles}&WIDTH={width}&HEIGHT={height}&FORMAT={service_format}'
        )
        return url

    def get_capabilities_url(self):
        """ Creates the url for the wms getCapabilities request.

        Returns:
            str: URL for getCapabilities request.
        """
        service = self.metadata.service
        uri = service.get_capabilities_uri_GET
        if uri is None:
            # Return None if uri is not defined so that service check fails
            return
        request_type = ServiceOperationEnum.GET_CAPABILITIES.value
        service_version = service.servicetype.version

        url = f'{uri}REQUEST={request_type}&VERSION={service_version}'
        return url

    def check_service(self, url: str):
        """ Checks the status of a service and calls the appropriate handlers.

        Args:
            url (str): URL of the service to check.
        Returns:
            nothing
        """
        service_status = Monitor.check_status(url)
        if service_status.success is True:
            self.handle_service_success(service_status)
        else:
            self.handle_service_error(service_status)

    @staticmethod
    def check_status(url: str) -> ServiceStatus:
        """ Check status of ogc service.

        Args:
            url (str): URL to the service that should be checked.
        Returns:
            ServiceStatus: Status info of service.
        """
        success = False
        duration = None
        connector = CommonConnector(url=url)
        try:
            connector.load()
        except Exception as e:
            # handler if server sends no response (e.g. outdated uri)
            response_text = str(e)
            return Monitor.ServiceStatus(success, response_text, connector.status_code, duration)

        duration = timedelta(seconds=connector.run_time)
        response_text = connector.text
        if connector.status_code == 200:
            success = True
            try:
                xml = parse_xml(response_text)
                if 'Exception' in xml.getroot().tag:
                    success = False
            except AttributeError:
                # handle successful responses that do not return xml
                response_text = None

        return Monitor.ServiceStatus(success, response_text, connector.status_code, duration)

    def handle_service_error(self, service_status: ServiceStatus):
        """ Handles service responses with error statuses.

        Args:
            service_status (ServiceStatus): Response of the status check.
        Returns:
            nothing
        """
        monitoring_result = MonitoringResult(
            monitoring_successful=service_status.success, metadata=self.metadata, needs_update=None,
            error_msg=service_status.message
        )
        monitoring_result.save()

    def handle_service_success(self, service_status: ServiceStatus):
        """ Handles service responses with success statuses.

        Args:
            service_status (ServiceStatus): Response of the status check.
        Returns:
            nothing
        """
        metadata_type = self.metadata.metadata_type.type.lower()
        if metadata_type == MetadataEnum.SERVICE.value.lower():
            document = Document.objects.get(related_metadata=self.metadata)
            current_document = document.current_capability_document
            crypto_handler = CryptoHandler()
            response_hash = crypto_handler.sha256(service_status.message)
            current_document_hash = crypto_handler.sha256(current_document)
            if response_hash == current_document_hash:
                monitoring_result = MonitoringResult(
                    monitoring_successful=service_status.success, metadata=self.metadata, needs_update=False,
                    duration=service_status.duration
                )
                monitoring_result.save()
            else:
                diff = difflib.unified_diff(current_document, service_status.message)
                monitoring_result = MonitoringResult(
                    monitoring_successful=service_status.success, metadata=self.metadata, needs_update=True,
                    duration=service_status.duration, diff=''.join(diff)
                )
                monitoring_result.save()
        else:
            monitoring_result = MonitoringResult(
                monitoring_successful=service_status.success, metadata=self.metadata, needs_update=False,
                duration=service_status.duration
            )
            monitoring_result.save()

