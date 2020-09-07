"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 14.07.20

"""
from celery import Task

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper, task_helper, service_helper
from service.helper.enums import OGCOperationEnum, MetadataEnum
from service.helper.ogc.ows import OGCWebService
from service.models import ExternalAuthentication, Metadata, MimeType, Keyword, Service, ServiceType, ServiceUrl
from service.settings import SERVICE_OPERATION_URI_TEMPLATE, SERVICE_METADATA_URI_TEMPLATE, HTML_METADATA_URI_TEMPLATE
from structure.models import MrMapUser, Organization, MrMapGroup


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
        self.formats_list = []

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
        self.get_service_operations_and_formats(xml_obj)

    def _create_contact_organization_record(self):
        """ Creates a contact record from the OGCWebFeatureService object

        Returns:
             contact (Contact): A persisted contact object
        """
        ## contact
        contact = Organization.objects.get_or_create(
            organization_name=self.service_provider_providername,
            person_name=self.service_provider_responsibleparty_individualname,
            email=self.service_provider_address_electronicmailaddress,
            phone=self.service_provider_telephone_voice,
            facsimile=self.service_provider_telephone_facsimile,
            city=self.service_provider_address_city,
            address=self.service_provider_address,
            postal_code=self.service_provider_address_postalcode,
            state_or_province=self.service_provider_address_state_or_province,
            country=self.service_provider_address_country,
        )[0]
        return contact

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
        md = Metadata()
        md_type = MetadataEnum.CATALOGUE.value
        md.metadata_type = md_type
        md.title = self.service_identification_title
        md.identifier = self.service_file_identifier
        md.abstract = self.service_identification_abstract
        md.online_resource = self.service_provider_onlineresource_linkage

        md.contact = self._create_contact_organization_record()
        md.authority_url = self.service_provider_url
        md.access_constraints = self.service_identification_accessconstraints
        md.fees = self.service_identification_fees
        md.created_by = register_group
        md.capabilities_original_uri = self.service_connect_url
        if self.service_bounding_box is not None:
            md.bounding_geometry = self.service_bounding_box

        # Save metadata record so we can use M2M or id of record later
        md.save()
        md.identifier = str(md.id) if md.identifier is None else md.identifier

        # Keywords
        for kw in self.service_identification_keywords:
            if kw is None:
                continue
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            md.keywords.add(keyword)

        md.formats.add(*self.formats_list)
        md.save()

        service = self._create_service_record(register_group, register_for_organization, md, is_update_candidate_for)

        return service

    def _create_service_record(self, group: MrMapGroup, orga_published_for: Organization, md: Metadata, is_update_candidate_for: Service):
        """ Creates a Service object from the OGCWebFeatureService object

        Args:
            group (MrMapGroup): The owner/creator group
            orga_published_for (Organization): The organization for which the service is published
            orga_publisher (Organization): THe organization that publishes
            md (Metadata): The describing metadata
        Returns:
             service (Service): The persisted service object
        """
        service = Service()
        service_type = ServiceType.objects.get_or_create(
            name=self.service_type.value,
            version=self.service_version.value
        )[0]
        service.service_type = service_type
        service.created_by = group
        service.published_for = orga_published_for

        service.availability = 0.0
        service.is_available = False
        service.is_root = True
        md.service = service
        service.is_update_candidate_for = is_update_candidate_for

        # Save record to enable M2M relations
        service.save()

        operation_urls = [
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                method="Get",
                url=self.get_capabilities_uri.get("get", None)
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                method="Post",
                url=self.get_capabilities_uri.get("post", None)
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_RECORD.value,
                method="Get",
                url=self.describe_record_uri.get("get", None)
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_RECORD.value,
                method="Post",
                url=self.describe_record_uri.get("post", None)
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_RECORDS.value,
                method="Get",
                url=self.get_records_uri.get("get", None)
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_RECORDS.value,
                method="Post",
                url=self.get_records_uri.get("post", None)
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_RECORD_BY_ID.value,
                method="Get",
                url=self.get_record_by_id_uri.get("get", None)
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_RECORD_BY_ID.value,
                method="Post",
                url=self.get_record_by_id_uri.get("post", None)
            )[0],
        ]
        service.operation_urls.add(*operation_urls)

        # Persist capabilities document
        service.persist_original_capabilities_doc(self.service_capabilities_xml)

        return service

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

    def get_service_operations_and_formats(self, xml_obj):
        """ Parses

        Args:
            xml_obj (Element): The xml as parsable element
        Returns:

        """
        from service.helper.service_helper import resolve_version_enum
        operation_obj = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("OperationsMetadata"),
            xml_obj
        )

        # Parse Operation metadata
        self._parse_operations_metadata(upper_elem=operation_obj)

        # Parse Service parameters
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

            parameters = self._parse_parameter_metadata(operation)
            output_format = parameters.get("outputFormat", None)
            if output_format is not None:
                self.formats_list.append(
                    MimeType.objects.get_or_create(
                        operation=operation_name,
                        mime_type=output_format,
                    )[0]
                )

    def _parse_parameter_metadata(self, upper_elem):
        """ Parses the <Parameter> elements inside of <OperationsMetadata>

        Args:
            upper_elem (Element): The upper xml element
        Returns:
            parameter_map (dict): Mapped parameters and values
        """
        parameter_objs = xml_helper.try_get_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Parameter"),
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

        return parameter_map
