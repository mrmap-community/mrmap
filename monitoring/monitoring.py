"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 09.12.2019

"""

from django.utils import timezone
import difflib
from typing import Union
from PIL import Image, UnidentifiedImageError
from io import BytesIO

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from monitoring.settings import MONITORING_REQUEST_TIMEOUT
from monitoring.models import Monitoring as MonitoringResult, MonitoringCapability, MonitoringRun, MonitoringSetting, \
    HealthState
from monitoring.helper.wmsHelper import WmsHelper
from monitoring.helper.wfsHelper import WfsHelper
from service.helper.crypto_handler import CryptoHandler
from service.helper.common_connector import CommonConnector
from service.helper.xml_helper import parse_xml
from service.models import Metadata, Document, Service, FeatureType
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, DocumentEnum


class Monitoring:

    def __init__(self, metadata: Metadata, monitoring_run: MonitoringRun, monitoring_setting: MonitoringSetting = None, ):
        self.metadata = metadata
        self.linked_metadata = None
        self.monitoring_run = monitoring_run
        self.monitoring_settings = monitoring_setting

    class ServiceStatus:
        """ Holds all required information about the service status.

        Attributes:
            monitored_uri (str): The used uri.
            success (bool): Success of the status. Holds True if service received a success status, False otherwise.
            status (int): The actual response status of the service.
            message (str): The response text of the request.
            duration (timedelta): The duration of the request.
        """
        def __init__(self, uri: str, success: bool, message: str, status: int = None, duration: timezone.timedelta = None):
            self.monitored_uri = uri
            self.success = success
            self.status = status
            self.message = message
            self.duration = duration

    @transaction.atomic
    def run_checks(self):
        """ Run checks for all ogc operations.

        Returns:
            nothing
        """

        try:
            check_obj = self.metadata.get_described_element()
        except ObjectDoesNotExist:
            pass

        if self.metadata.is_service_metadata:
            if self.metadata.is_service_type(OGCServiceEnum.WMS):
                self.check_wms(check_obj)
            elif self.metadata.is_service_type(OGCServiceEnum.WFS):
                self.check_wfs(check_obj)

        elif self.metadata.is_layer_metadata:
            self.check_layer(check_obj)
        elif self.metadata.is_featuretype_metadata:
            self.check_featuretype(check_obj)
        elif self.metadata.is_dataset_metadata:
            self.check_dataset()

        # all checks are done. Calculate the health state for all monitoring results
        health_state = HealthState(monitoring_run=self.monitoring_run, metadata=self.metadata)
        health_state.save()
        health_state.run_health_state()

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
        version = service.service_type.version

        if wfs_helper.get_capabilities_url is not None:
            self.check_get_capabilities(wfs_helper.get_capabilities_url)

            if version == OGCServiceVersionEnum.V_2_0_0.value:
                wfs_helper.set_2_0_0_urls()
                if wfs_helper.list_stored_queries is not None:
                    self.check_service(wfs_helper.list_stored_queries)

            if version == OGCServiceVersionEnum.V_2_0_2.value:
                wfs_helper.set_2_0_2_urls()
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

        if wms_helper.get_capabilities_url is not None:
            self.check_get_capabilities(wms_helper.get_capabilities_url)
        if not capabilities_only:
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

    def check_layer(self, service: Service):
        """" Checks the status of a layer.

        Args:
            service (Service): The service to check.
        Returns:
            nothing
        """
        wms_helper = WmsHelper(service)
        urls_to_check = [
            (wms_helper.get_get_map_url(), True),
            (wms_helper.get_get_styles_url(), False),
            (wms_helper.get_get_feature_info_url(), False),
            (wms_helper.get_describe_layer_url(), False),
        ]
        for url in urls_to_check:
            if url[0] is None:
                continue
            self.check_service(url[0], check_image=url[1])

    def check_featuretype(self, feature_type: FeatureType):
        """ Checks the status of a featuretype.

        Args:
            feature_type (FeatureType): The featuretype to check.
        Returns:
            nothing
        """
        wfs_helper = WfsHelper(feature_type)
        urls_to_check = [
            (wfs_helper.get_describe_featuretype_url(feature_type.metadata.identifier), True),
            (wfs_helper.get_get_feature_url(feature_type.metadata.identifier), True),
        ]
        for url in urls_to_check:
            if url[0] is None:
                continue
            self.check_service(url[0], check_wfs_member=url[1])

    def check_service(self, url: str, check_wfs_member: bool = False, check_image: bool = False):
        """ Checks the status of a service and calls the appropriate handlers.

        Args:
            url (str): URL of the service to check.
            check_wfs_member (bool): True, if a returned xml should check for a 'member' tag.
            check_image (bool): True, if the returned content should be checked as image.
        Returns:
            nothing
        """
        service_status = self.check_status(url, check_wfs_member=check_wfs_member, check_image=check_image)
        if service_status.success is True:
            self.handle_service_success(service_status)
        else:
            self.handle_service_error(service_status)

    def check_status(self, url: str, check_wfs_member: bool = False, check_image: bool = False) -> ServiceStatus:
        """ Check status of ogc service.

        Args:
            url (str): URL to the service that should be checked.
            check_wfs_member (bool): True, if a returned xml should check for a 'member' tag.
            check_image (bool): True, if the returned content should be checked as image.
        Returns:
            ServiceStatus: Status info of service.
        """
        success = False
        duration = None
        connector = CommonConnector(url=url, timeout=self.monitoring_settings.timeout if self.monitoring_settings is not None else MONITORING_REQUEST_TIMEOUT)
        if self.metadata.has_external_authentication:
            connector.external_auth = self.metadata.external_authentication
        try:
            connector.load()
        except Exception as e:
            # handler if server sends no response (e.g. outdated uri)
            response_text = str(e)
            return Monitoring.ServiceStatus(url, success, response_text, connector.status_code, duration)

        duration = timezone.timedelta(seconds=connector.run_time)
        response_text = connector.content
        if connector.status_code == 200:
            success = True
            try:
                xml = parse_xml(response_text)
                if 'Exception' in xml.getroot().tag:
                    success = False
                if check_wfs_member:
                    if not self.has_wfs_member(xml):
                        success = False
            except AttributeError:
                # handle successful responses that do not return xml
                response_text = None
            if check_image:
                try:
                    Image.open(BytesIO(connector.content))
                    success = True
                except UnidentifiedImageError:
                    success = False
        service_status = Monitoring.ServiceStatus(url, success, response_text, connector.status_code, duration)
        return service_status

    def has_wfs_member(self, xml):
        """Checks the existence of a (feature)Member for a wfs feature.

        Args:
            xml (object): Xml object
        Returns:
            bool: true, if xml has member, false otherwise
        """
        service = self.metadata.service
        version = service.service_type.version
        if version == OGCServiceVersionEnum.V_1_0_0.value:
            return len([child for child in xml.getroot() if child.tag.endswith('featureMember')]) != 1
        if version == OGCServiceVersionEnum.V_1_1_0.value:
            return len([child for child in xml.getroot() if child.tag.endswith('featureMember')]) != 1
        if version == OGCServiceVersionEnum.V_2_0_0.value:
            return len([child for child in xml.getroot() if child.tag.endswith('member')]) != 1
        if version == OGCServiceVersionEnum.V_2_0_2.value:
            return len([child for child in xml.getroot() if child.tag.endswith('member')]) != 1

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
        document = Document.objects.get(
            metadata=self.metadata,
            is_original=True,
            document_type=DocumentEnum.CAPABILITY.value
        )
        original_document = document.content
        self.check_document(url, original_document)

    def check_dataset(self):
        """Handles the dataset checks.

        Handles the monitoring process of the datasets as the workflow differs from other operations.
        If the service is available, a MonitoringCapability model instance will be created and stored in the db. Set
        values depend on possible differences in the retrieved dataset document.
        If the service is not available, a Monitoring model instance will be created as no information on
        differences between datset documents is given.

        Args:
            none
        Returns:
            nothing
        """
        url = self.metadata.metadata_url
        document = Document.objects.get(
            metadata=self.metadata,
            document_type=DocumentEnum.METADATA.value,
            is_original=True,
        )
        original_document = document.content
        self.check_document(url, original_document)

    def check_document(self, url, original_document):
        service_status = self.check_status(url)
        if service_status.success:
            diff_obj = self.get_document_diff(service_status.message, original_document)
            if diff_obj is not None:
                needs_update = True
                diff = ''.join(diff_obj)
                monitoring_capability = MonitoringCapability(
                    available=service_status.success, metadata=self.metadata, status_code=service_status.status,
                    duration=service_status.duration, monitored_uri=service_status.monitored_uri, diff=diff,
                    needs_update=needs_update, monitoring_run=self.monitoring_run,
                )
            else:
                needs_update = False
                monitoring_capability = MonitoringCapability(
                    available=service_status.success, metadata=self.metadata, status_code=service_status.status,
                    duration=service_status.duration, monitored_uri=service_status.monitored_uri,
                    needs_update=needs_update, monitoring_run=self.monitoring_run,
                )
            monitoring_capability.save()
        else:
            self.handle_service_error(service_status)

    def get_document_diff(self, new_document: str, original_document: str) -> Union[str, None]:
        """Computes the diff between two documents.

        Compares the currently stored document and compares its hash to the one
        in the response of the latest check.

        Args:
            new_document (str): Document of last request.
            original_document (str): Original document.
        Returns:
            str: The diff of the two documents, if hashes have differences
            None: If the hashes have no differences
        """
        crypto_handler = CryptoHandler()
        try:
            # check if new_capabilities is bytestring and decode it if so
            new_document = new_document.decode('UTF-8')
        except AttributeError:
            pass
        new_capabilities_hash = crypto_handler.sha256(new_document)
        original_document_hash = crypto_handler.sha256(original_document)
        if new_capabilities_hash == original_document_hash:
            return
        else:
            original_lines = original_document.splitlines(keepends=True)
            new_lines = new_document.splitlines(keepends=True)
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
                monitoring_run=self.monitoring_run,
            )
        else:
            monitoring_result = MonitoringResult(
                available=service_status.success, metadata=self.metadata, status_code=service_status.status,
                error_msg=service_status.message, monitored_uri=service_status.monitored_uri,
                duration=service_status.duration, monitoring_run=self.monitoring_run,
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
            available=service_status.success,
            metadata=self.metadata,
            status_code=service_status.status,
            duration=service_status.duration,
            monitored_uri=service_status.monitored_uri,
            monitoring_run=self.monitoring_run,
        )
        monitoring_result.save()
