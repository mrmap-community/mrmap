"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 14.07.20

"""
from celery import Task

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper, task_helper, service_helper
from service.helper.enums import OGCOperationEnum
from service.helper.ogc.ows import OGCWebService
from service.models import ExternalAuthentication
from structure.models import MrMapUser


class OGCCatalogueService(OGCWebService):
    """ An internal representation of the OGC CSW

    """
    def __init__(self, service_connect_url, service_version, service_type, external_auth: ExternalAuthentication):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=service_version,
            service_type=service_type,
            external_auth=external_auth
        )

        self.get_capabilities_uri = {
            "get": None,
            "post": None,
        }
        self.describe_record_uri = {
            "get": None,
            "post": None,
        }
        self.get_records_uri = {
            "get": None,
            "post": None,
        }
        self.get_record_by_id_uri = {
            "get": None,
            "post": None,
        }

    def create_from_capabilities(self, metadata_only: bool = False, async_task: Task = None, external_auth: ExternalAuthentication = None):
        """ Load data from capabilities document

        Args:
            metadata_only (bool): Whether only metadata shall be fetched
            async_task (Task): The asynchronous running task
        Returns:

        """
        # get xml as iterable object
        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)

        # parse service metadata
        self.get_service_metadata_from_capabilities(xml_obj, async_task)

        # Parse <OperationsMetadata>
        self.get_service_operations(xml_obj)

    def create_service_model_instance(self, user: MrMapUser, register_group, register_for_organization, external_auth, is_update_candidate_for):
        """ Map all data from the OGCCatalogueService class to their database models

        Args:
            user (MrMapUser): The user which performs the action
            register_group (Group): The group which is used to register this service
            register_for_organization (Organization): The organization for which this service is being registered
            external_auth (ExternalAuthentication): The external authentication object
        Returns:
             service (Service): Service instance, contains all information, ready for persisting!
        """
        i = 0

    def get_service_metadata_from_capabilities(self, xml_obj, async_task: Task = None):
        """ Parse the capability document <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        service_xml = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("ServiceIdentification"),
            xml_obj
        )
        self.service_identification_title = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Title")
        )

        if async_task is not None:
            task_helper.update_service_description(async_task, self.service_identification_title, phase_descr="Parsing main capabilities")

        self.service_identification_abstract = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Abstract")
        )

        self.service_identification_fees = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Fees")
        )

        self.service_identification_accessconstraints = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("AccessConstraints")
        )

        keywords = xml_helper.try_get_element_from_xml(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Keywords") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("Keyword")
        )
        kw = []
        for keyword in keywords:
            text = keyword.text
            if text is None:
                continue
            try:
                kw.append(text)
            except AttributeError:
                pass
        self.service_identification_keywords = kw

        self.service_provider_providername = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("ProviderName")
        )

        provider_site_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("ProviderSite"),
            xml_obj
        )
        self.service_provider_url = xml_helper.get_href_attribute(xml_elem=provider_site_elem)
        self.service_provider_responsibleparty_individualname = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("IndividualName")
        )
        self.service_provider_responsibleparty_positionname = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("PositionName")
        )
        self.service_provider_telephone_voice = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Voice")
        )
        self.service_provider_telephone_facsimile = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Facsimile")
        )
        self.service_provider_address = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("DeliveryPoint")
        )
        self.service_provider_address_city = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("City")
        )
        self.service_provider_address_state_or_province = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("AdministrativeArea")
        )
        self.service_provider_address_postalcode = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("PostalCode")
        )
        self.service_provider_address_country = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Country")
        )
        self.service_provider_address_electronicmailaddress = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("ElectronicMailAddress")
        )
        online_resource_elem = xml_helper.try_get_single_element_from_xml(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
        )
        self.service_provider_onlineresource_linkage = xml_helper.get_href_attribute(online_resource_elem)
        if self.service_provider_onlineresource_linkage is None or self.service_provider_onlineresource_linkage == "":
            # There are metadatas where no online resource link is given. We need to generate it manually therefore...
            self.service_provider_onlineresource_linkage = service_helper.split_service_uri(self.service_connect_url).get("base_uri")
            self.service_provider_onlineresource_linkage = service_helper.prepare_original_uri_stump(self.service_provider_onlineresource_linkage)

        self.service_provider_contact_hoursofservice = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("HoursOfService")
        )
        self.service_provider_contact_contactinstructions = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInstructions")
        )

    def get_service_operations(self, xml_obj):
        """ Parses

        Args:
            xml_obj (Element): The xml as parsable element
        Returns:

        """
        operation_obj = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("OperationsMetadata"),
            xml_obj
        )

        self._parse_operations_metadata(upper_elem=operation_obj)
        self._parse_parameter_metadata(upper_elem=operation_obj)

    def _parse_operations_metadata(self, upper_elem):
        """ Parses the <Operation> elements inside of <OperationsMetadata>

        Args:
            upper_elem (Element): The upper xml element
        Returns:

        """
        operations_objs = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation"),
            upper_elem
        )

        operation_map = {
            OGCOperationEnum.GET_CAPABILITIES.value: self.get_capabilities_uri,
            OGCOperationEnum.DESCRIBE_RECORD.value: self.describe_record_uri,
            OGCOperationEnum.GET_RECORDS.value: self.get_records_uri,
            OGCOperationEnum.GET_RECORD_BY_ID.value: self.get_record_by_id_uri,
        }

        for operation in operations_objs:
            operation_name = xml_helper.try_get_attribute_from_xml_element(
                operation,
                "name",
            )
            get_uri = xml_helper.try_get_single_element_from_xml(
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
                operation
            )
            get_uri = xml_helper.get_href_attribute(get_uri) if get_uri is not None else None

            post_uri = xml_helper.try_get_single_element_from_xml(
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
                operation
            )
            post_uri = xml_helper.get_href_attribute(post_uri) if post_uri is not None else None

            uri_dict = operation_map.get(operation_name, {})
            uri_dict["get"] = get_uri
            uri_dict["post"] = post_uri

    def _parse_parameter_metadata(self, upper_elem):
        """ Parses the <Parameter> elements inside of <OperationsMetadata>

        Args:
            upper_elem (Element): The upper xml element
        Returns:

        """
        parameter_objs = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Parameter"),
            upper_elem
        )
        parameter_map = {}
        for parameter in parameter_objs:
            param_name = xml_helper.try_get_attribute_from_xml_element(
                parameter,
                "name"
            )
            param_val = xml_helper.try_get_text_from_xml_element(
                parameter,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Value")
            )
            parameter_map[param_name] = param_val

        self.service_version = parameter_map.get("version", None)
