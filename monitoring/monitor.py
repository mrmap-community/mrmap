"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 09.12.2019

"""
from datetime import timedelta
import difflib

from MapSkinner.utils import sha256
from monitoring.models import MonitoringResult
from service.helper.common_connector import CommonConnector
from service.helper.xml_helper import parse_xml
from service.models import Metadata, Document


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
        if self.metadata.metadata_type.type.lower() == 'layer':
            # TODO add get_feature_info
            # TODO add get_legend_graphic
            # TODO add get_map
            # TODO get_styles
            pass
        elif self.metadata.metadata_type.type.lower() == 'service':
            service_type = self.metadata.service.servicetype.name.lower()
            if (service_type == 'wms') or (service_type == 'wfs'):
                url = self.get_capabilities_url()
                self.check_service(url)

    def get_capabilities_url(self):
        """ Creates the url for the wms getCapabilities request.

        Returns:
            str: URL for getCapabilities request.
        """
        service = self.metadata.service
        uri = service.get_capabilities_uri
        request_type = 'GetCapabilities'
        service_type = service.servicetype.name
        service_version = service.servicetype.version

        if uri is None:
            # TODO what should happen if service is None?
            print(
                "get_capabilities_uri is None for metadata id {}. Using capabilities_original_uri instead.".format(
                    self.metadata.pk
                )
            )
            return self.metadata.capabilities_original_uri
        url = '{}?SERVICE={}&REQUEST={}&VERSION={}'.format(uri, service_type, request_type, service_version)
        return url

    def check_service(self, url: str):
        """ Checks the status of a service and calls the appropriate handlers.

        Args:
            url (str): URL of the service to check.
        Returns:
            nothing
        """
        service_status = self.check_status(url)
        if service_status.success is True:
            self.handle_service_success(service_status)
        else:
            self.handle_service_error(service_status)

    def check_status(self, url: str) -> ServiceStatus:
        """ Check status of ogc service.

        Args:
            url (str): URL to the service that should be checked.
        Returns:
            ServiceStatus: Status info of service.
        """
        success = False
        response_text = None
        duration = None
        connector = CommonConnector(url=url)
        try:
            connector.load()
        except Exception as e:
            response_text = str(e)

        if response_text is None:
            response_text = connector.text
        if connector.status_code == 200:
            success = True
            duration = timedelta(seconds=connector.load_time)
            xml = parse_xml(response_text)
            if 'Exception' in xml.getroot().tag:
                success = False

        return Monitor.ServiceStatus(success, response_text, connector.status_code, duration)

    def handle_service_error(self, service_status: ServiceStatus):
        """ Handles service responses with error statuses.

        Args:
            service_status (ServiceStatus): Response of the status check.
        Returns:
            nothing
        """
        monitoring_result = MonitoringResult(
            metadata=self.metadata, needs_update=None, error_msg=service_status.message
        )
        monitoring_result.save()

    def handle_service_success(self, service_status: ServiceStatus):
        """ Handles service responses with success statuses.

        Args:
            service_status (ServiceStatus): Response of the status check.
        Returns:
            nothing
        """
        document = Document.objects.get(related_metadata=self.metadata)
        current_document = document.current_capability_document
        response_hash = sha256(service_status.message)
        current_document_hash = sha256(current_document)
        if response_hash == current_document_hash:
            monitoring_result = MonitoringResult(
                metadata=self.metadata, needs_update=False, duration=service_status.duration
            )
            monitoring_result.save()
        else:
            diff = difflib.unified_diff(current_document, service_status.message)
            monitoring_result = MonitoringResult(
                metadata=self.metadata, needs_update=True, duration=service_status.duration, diff=''.join(diff)
            )
            monitoring_result.save()

