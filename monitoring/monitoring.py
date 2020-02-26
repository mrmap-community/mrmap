"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 09.12.2019

"""
from datetime import timedelta
import difflib
from typing import Union

from django.core.exceptions import ObjectDoesNotExist

from monitoring.models import Monitoring as MonitoringResult, MonitoringCapability, MonitoringRun
from monitoring.helper.wmsHelper import WmsHelper
from monitoring.helper.wfsHelper import WfsHelper
from service.helper.crypto_handler import CryptoHandler
from service.helper.common_connector import CommonConnector
from service.helper.xml_helper import parse_xml
from service.models import Metadata, Document, Service, MetadataRelation
from service.helper.enums import OGCServiceEnum, MetadataEnum, OGCServiceVersionEnum


class Monitoring:

    def __init__(self, metadata: Metadata, monitoring_run: MonitoringRun):
        self.metadata = metadata
        self.linked_metadata = None
        self.monitoring_run = monitoring_run
        # NOTE: Since there is no clear handling for which setting to use,
        # we will always use the first (default) setting.
        self.monitoring_settings = metadata.monitoring_setting.first()

    class ServiceStatus:
        """ Holds all required information about the service status.

        Attributes:
            monitored_uri (str): The used uri.
            success (bool): Success of the status. Holds True if service received a success status, False otherwise.
            status (int): The actual response status of the service.
            message (str): The response text of the request.
            duration (timedelta): The duration of the request.
        """
        def __init__(self, uri: str, success: bool, message: str, status: int = None, duration: timedelta = None):
            self.monitored_uri = uri
            self.success = success
            self.status = status
            self.message = message
            self.duration = duration

    def run_checks(self):
        """ Run checks for all ogc operations.

        Returns:
            nothing
        """
        self.get_linked_metadata()
        has_service = True

        try:
            service = self.metadata.service
        except ObjectDoesNotExist:
            has_service = False

        if has_service:
            metadata_type = self.metadata.metadata_type.type.lower()

            if metadata_type == MetadataEnum.SERVICE.value.lower():
                service_type = service.servicetype.name.lower()
                if service_type == OGCServiceEnum.WMS.value.lower():
                    self.check_wms(service, True)
                elif service_type == OGCServiceEnum.WFS.value.lower():
                    self.check_wfs(service)

            elif metadata_type == MetadataEnum.LAYER.value.lower():

                service_type = service.servicetype.name.lower()
                if service_type == OGCServiceEnum.WMS.value.lower():
                    self.check_wms(service)
                elif service_type == OGCServiceEnum.WFS.value.lower():
                    self.check_wfs(service)

            elif metadata_type == MetadataEnum.FEATURETYPE.value.lower():
                pass
            elif metadata_type == MetadataEnum.DATASET.value.lower():
                pass

        self.check_linked_metadata()

    def get_linked_metadata(self):
        """ Gets the to the current metadata linked metadata.

        Returns
            nothing
        """
        self.linked_metadata = MetadataRelation.objects.filter(metadata_from=self.metadata)

    def check_linked_metadata(self):
        for metadata_relation in self.linked_metadata:
            monitoring = Monitoring(metadata_relation.metadata_to)
            monitoring.run_checks()

    def check_wfs(self, service: Service):
        """ Check the availability of wfs operations.

        Checks for each read-only wfs operation if that operation is active. Version specific operations will
        be distinguished. As no featureTypes are stored in the metadata relation, only operations that do not
        require information about a specific featureType will be checked.

        Args:
            service (Service): The service metadata which will be used for building the operation specific uris.
        Returns:
            nothing
        """
        wfs_helper = WfsHelper(service)
        version = service.servicetype.version

        if wfs_helper.get_capabilities_url is not None:
            self.check_get_capabilities(wfs_helper.get_capabilities_url)

            if version == OGCServiceVersionEnum.V_2_0_0.value:
                wfs_helper.set_2_0_0_urls()
                if wfs_helper.list_stored_queries is not None:
                    self.check_service(wfs_helper.list_stored_queries)

    def check_wms(self, service: Service, capabilities_only: bool = False):
        """ Check the availability of wms operations.

        Checks for each wms operation if that operation is active. Either only the getCapabilities operation will be
        checked or all other operations. This should reduce the number of requests as the availability of the
        getCapabilities is not specific for every given layer.

        Args:
            service (Service): The service metadata which will be used for building the operation specific uris.
            capabilities_only (bool): Flag if only getCapabilities or all other operations should be checked.
        Returns:
            nothing
        """
        wms_helper = WmsHelper(service)

        if capabilities_only:
            if wms_helper.get_capabilities_url is not None:
                self.check_get_capabilities(wms_helper.get_capabilities_url)
        else:
            wms_helper.set_operation_urls()
            if wms_helper.get_map_url is not None:
                self.check_service(wms_helper.get_map_url)

            if wms_helper.get_feature_info_url is not None:
                self.check_service(wms_helper.get_feature_info_url)

            if wms_helper.describe_layer_url is not None:
                self.check_service(wms_helper.describe_layer_url)

            if wms_helper.get_legend_graphic_url is not None:
                self.check_service(wms_helper.get_legend_graphic_url)

            if wms_helper.get_styles_url is not None:
                self.check_service(wms_helper.get_styles_url)

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
        duration = None
        connector = CommonConnector(url=url, timeout=self.monitoring_settings.timeout)
        if self.metadata.has_external_authentication():
            connector.external_auth = self.metadata.external_authentication
        try:
            connector.load()
        except Exception as e:
            # handler if server sends no response (e.g. outdated uri)
            response_text = str(e)
            return Monitoring.ServiceStatus(url, success, response_text, connector.status_code, duration)

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

        return Monitoring.ServiceStatus(url, success, response_text, connector.status_code, duration)

    def check_get_capabilities(self, url: str):
        """Handles the GetCapabilities checks.

        Handles the monitoring process of the GetCapabilities operation as the workflow differs from other operations.
        If the service is available, a MonitoringCapability model instance will be created and stored in the db. Set
        values depend on possible differences in the retrieved capabilities document.
        If the service is not available, a Monitoring model instance will be created as no information on
        differences between capabilities documents is given.

        Args:
            url (str): The url for the GetCapabilities request.
        Returns:
            nothing
        """
        service_status = self.check_status(url)
        if service_status.success:
            diff_obj = self.get_capabilities_diff(service_status.message)
            if diff_obj is not None:
                needs_update = True
                diff = ''.join(diff_obj)
                monitoring_capability = MonitoringCapability(
                    available=service_status.success, metadata=self.metadata, status_code=service_status.status,
                    duration=service_status.duration, monitored_uri=service_status.monitored_uri, diff=diff,
                    needs_update=needs_update, monitoring_run=self.monitoring_run
                )
            else:
                needs_update = False
                monitoring_capability = MonitoringCapability(
                    available=service_status.success, metadata=self.metadata, status_code=service_status.status,
                    duration=service_status.duration, monitored_uri=service_status.monitored_uri,
                    needs_update=needs_update, monitoring_run=self.monitoring_run
                )
            monitoring_capability.save()
        else:
            self.handle_service_error(service_status)

    def get_capabilities_diff(self, new_capabilities: str) -> Union[str, None]:
        """Computes the diff between two capabilities documents.

        Retrieves the currently stored capabilities document and compares its hash to the one
        in the response of the latest getCapabilities check.

        Args:
            new_capabilities (str): GetCapabilities document of last request.
        Returns:
            str: The diff of the two capabilities documents, if hashes have differences
            None: If the hashes have no differences
        """
        document = Document.objects.get(related_metadata=self.metadata)
        original_document = document.original_capability_document
        crypto_handler = CryptoHandler()
        new_capabilities_hash = crypto_handler.sha256(new_capabilities)
        original_document_hash = crypto_handler.sha256(original_document)
        if new_capabilities_hash == original_document_hash:
            return
        else:
            original_lines = original_document.splitlines(keepends=True)
            new_lines = new_capabilities.splitlines(keepends=True)
            # info on the created diff on https://docs.python.org/3.6/library/difflib.html#difflib.unified_diff
            diff = difflib.unified_diff(original_lines, new_lines)
            return diff

    def handle_service_error(self, service_status: ServiceStatus):
        """ Handles service responses with error statuses.

        Args:
            service_status (ServiceStatus): Response of the status check.
        Returns:
            nothing
        """
        if service_status.duration is None:
            monitoring_result = MonitoringResult(
                available=service_status.success, metadata=self.metadata, status_code=service_status.status,
                error_msg=service_status.message, monitored_uri=service_status.monitored_uri,
                monitoring_run=self.monitoring_run
            )
        else:
            monitoring_result = MonitoringResult(
                available=service_status.success, metadata=self.metadata, status_code=service_status.status,
                error_msg=service_status.message, monitored_uri=service_status.monitored_uri,
                duration=service_status.duration, monitoring_run=self.monitoring_run
            )

        monitoring_result.save()

    def handle_service_success(self, service_status: ServiceStatus):
        """ Handles service responses with success statuses.

        Args:
            service_status (ServiceStatus): Response of the status check.
        Returns:
            nothing
        """
        monitoring_result = MonitoringResult(
            available=service_status.success, metadata=self.metadata, status_code=service_status.status,
            duration=service_status.duration, monitored_uri=service_status.monitored_uri,
            monitoring_run=self.monitoring_run
        )
        monitoring_result.save()
