"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 09.12.2019

"""
import difflib
import hashlib
from io import BytesIO
from typing import Union

from PIL import Image
from PIL import UnidentifiedImageError
from django.db import transaction
from django.utils import timezone
from lxml import etree
from lxml.etree import XMLSyntaxError
from requests import Request

from MrMap.settings import PROXIES
from monitoring.helper.wfsHelper import WfsHelper
from monitoring.helper.wmsHelper import WmsHelper
from monitoring.models import MonitoringResult as MonitoringResult, MonitoringResultDocument, MonitoringRun, \
    MonitoringSetting, \
    HealthState
from monitoring.settings import MONITORING_REQUEST_TIMEOUT
from resourceNew.enums.service import OGCServiceVersionEnum, OGCServiceEnum
from resourceNew.models import Service, Layer, FeatureType, DatasetMetadata


class Monitoring:

    def __init__(self, resource: Union[Service, Layer, FeatureType, DatasetMetadata], monitoring_run: MonitoringRun,
                 monitoring_setting: MonitoringSetting = None, ):
        self.resource = resource
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

        def __init__(self, uri: str, success: bool, message: str, status: int = None,
                     duration: timezone.timedelta = None):
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

        if isinstance(self.resource, Service):
            if self.resource.is_service_type(OGCServiceEnum.WMS):
                self.check_wms(self.resource)
            elif self.resource.is_service_type(OGCServiceEnum.WFS):
                self.check_wfs(self.resource)
        elif isinstance(self.resource, Layer):
            self.check_layer(self.resource)
        elif isinstance(self.resource, FeatureType):
            self.check_featuretype(self.resource)
        elif isinstance(self.resource, DatasetMetadata):
            self.check_dataset(self.resource)
        else:
            raise ValueError(f"Unexpected resource type {self.resource.__class__.__name__}")

        # all checks are done. Calculate the health state for all monitoring results
        health_state = HealthState(monitoring_run=self.monitoring_run,
                                   resource=self.resource,
                                   created_by_user=self.monitoring_run.created_by_user,
                                   owned_by_org=self.monitoring_run.owned_by_org)
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

    def check_layer(self, layer: Layer):
        """" Checks the status of a layer.

        Args:
            layer (Layer): The service to check.
        Returns:
            nothing
        """
        wms_helper = WmsHelper(layer.service)
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
        wfs_helper = WfsHelper(feature_type.service)
        urls_to_check = [
            (wfs_helper.get_describe_featuretype_url(feature_type.identifier), True),
            (wfs_helper.get_get_feature_url(feature_type.identifier), True),
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
        service = self.resource if isinstance(self.resource, Service) else self.resource.service
        session = service.get_session_for_request()
        timeout = MONITORING_REQUEST_TIMEOUT if self.monitoring_settings is None else self.monitoring_settings.timeout
        request = Request(method="GET",
                          url=url)
        response = session.send(request.prepare(), timeout=timeout)
        duration = response.elapsed
        response_text = response.content

        if response.status_code != 200:
            response_text = f"Unexpected HTTP response code: {response.status_code}"
            return Monitoring.ServiceStatus(url, success, response_text, response.status_code, duration)

        success = True
        try:
            xml = self.parse_xml(response.content)
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
                Image.open(BytesIO(response.content))
                success = True
            except UnidentifiedImageError:
                success = False
        service_status = Monitoring.ServiceStatus(url, success, response_text, response.status_code, duration)
        return service_status

    def has_wfs_member(self, xml):
        """Checks the existence of a (feature)Member for a wfs feature.

        Args:
            xml (object): Xml object
        Returns:
            bool: true, if xml has member, false otherwise
        """
        service = self.resource
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
        original_document = self.resource.xml_backup_string
        self.check_document(url, original_document)

    def check_dataset(self, dataset: DatasetMetadata):
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
        # TODO handle None
        url = dataset.origin_url
        current_document = dataset.xml
        self.check_document(url, current_document)

    def check_document(self, url, original_document):
        service_status = self.check_status(url)
        if service_status.success:
            diff_obj = self.get_document_diff(service_status.message, original_document)
            if diff_obj is not None:
                needs_update = True
                diff = ''.join(diff_obj)
                monitoring_document = MonitoringResultDocument(
                    available=service_status.success, resource=self.resource, status_code=service_status.status,
                    duration=service_status.duration, monitored_uri=service_status.monitored_uri, diff=diff,
                    needs_update=needs_update, monitoring_run=self.monitoring_run,
                    created_by_user=self.monitoring_run.created_by_user,
                    owned_by_org=self.monitoring_run.owned_by_org
                )
            else:
                needs_update = False
                monitoring_document = MonitoringResultDocument(
                    available=service_status.success, resource=self.resource, status_code=service_status.status,
                    duration=service_status.duration, monitored_uri=service_status.monitored_uri,
                    needs_update=needs_update, monitoring_run=self.monitoring_run,
                    created_by_user=self.monitoring_run.created_by_user,
                    owned_by_org=self.monitoring_run.owned_by_org
                )
            monitoring_document.save()
        else:
            self.handle_service_error(service_status)

    def get_document_diff(self, new_document: str, original_document: bytes) -> Union[str, None]:
        """Computes the diff between two documents.

        Compares the currently stored document and compares its hash to the one
        in the response of the latest check.

        Args:
            new_document (str): Document of last request.
            original_document (bytes): Original document.
        Returns:
            str: The diff of the two documents, if hashes have differences
            None: If the hashes have no differences
        """
        try:
            # check if new_capabilities is bytestring and decode it if so
            new_document = new_document.decode('UTF-8')
        except AttributeError:
            pass
        new_capabilities_hash = hashlib.sha256(new_document.encode("UTF-8")).hexdigest()
        original_document_hash = hashlib.sha256(original_document).hexdigest()
        if new_capabilities_hash == original_document_hash:
            return
        else:
            original_lines = original_document.decode('UTF-8').splitlines(keepends=True)
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
                available=service_status.success, resource=self.resource, status_code=service_status.status,
                error_msg=service_status.message, monitored_uri=service_status.monitored_uri,
                monitoring_run=self.monitoring_run, created_by_user=self.monitoring_run.created_by_user,
                owned_by_org=self.monitoring_run.owned_by_org
            )
        else:
            monitoring_result = MonitoringResult(
                available=service_status.success, resource=self.resource, status_code=service_status.status,
                error_msg=service_status.message, monitored_uri=service_status.monitored_uri,
                duration=service_status.duration, monitoring_run=self.monitoring_run,
                created_by_user=self.monitoring_run.created_by_user,
                owned_by_org=self.monitoring_run.owned_by_org
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
            resource=self.resource,
            status_code=service_status.status,
            duration=service_status.duration,
            monitored_uri=service_status.monitored_uri,
            monitoring_run=self.monitoring_run,
            created_by_user=self.monitoring_run.created_by_user,
            owned_by_org=self.monitoring_run.owned_by_org
        )
        monitoring_result.save()

    def parse_xml(self, xml: str, encoding=None):
        """ Returns the xml as iterable object
        Args:
            xml(str): The xml as string
        Returns:
            nothing
        """
        if not isinstance(xml, str) and not isinstance(xml, bytes):
            raise ValueError
        default_encoding = "UTF-8"
        if not isinstance(xml, bytes):
            if encoding is None:
                xml_b = xml.encode(default_encoding)
            else:
                xml_b = xml.encode(encoding)
        else:
            xml_b = xml
        try:
            parser = etree.XMLParser(huge_tree=len(xml_b) > 10000000)
            xml_obj = etree.ElementTree(etree.fromstring(text=xml_b, parser=parser))
            if encoding != xml_obj.docinfo.encoding:
                # there might be problems e.g. with german Umlaute ä,ö,ü, ...
                # try to parse again but with the correct encoding
                return self.parse_xml(xml, xml_obj.docinfo.encoding)
        except XMLSyntaxError as e:
            xml_obj = None
        return xml_obj
