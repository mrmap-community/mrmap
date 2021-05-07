# common classes for handling of OWS (OGC Webservices)
# for naming conventions see http://portal.opengeospatial.org/files/?artifact_id=38867
from abc import abstractmethod, ABC
from urllib.parse import urlencode

from django.contrib.gis.geos import Polygon
from lxml.etree import Element
from requests.exceptions import ReadTimeout

from MrMap.messages import CONNECTION_TIMEOUT
from MrMap.settings import XML_NAMESPACES
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionEnum, OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum
from service.helper.iso.iso_19115_metadata_parser import ISOMetadata
from service.models import ExternalAuthentication, Service
from structure.models import Organization


class OGCWebService(ABC):
    """ The base class for all derived web services

    """

    def __init__(self,
                 service_connect_url=None,
                 service_type=OGCServiceEnum.WMS,
                 service_version=OGCServiceVersionEnum.V_1_1_1,
                 service_capabilities_xml=None,
                 external_auth: ExternalAuthentication = None):
        self.service_connect_url = service_connect_url
        self.service_type = service_type  # wms, wfs, wcs, ...
        self.service_version = service_version  # 1.0.0, 1.1.0, ...
        self.service_capabilities_xml = service_capabilities_xml
        self.external_authentification = external_auth
        self.descriptive_document_encoding = None
        self.connect_duration = None
        self.service_object = None

        # service_metadata
        self.service_file_identifier = None
        self.service_file_iso_identifier = None
        self.service_preview_image = None
        self.service_iso_md_uri = None
        self.service_identification_title = None
        self.service_identification_abstract = None
        self.service_identification_keywords = []
        self.service_identification_fees = None
        self.service_identification_accessconstraints = None

        self.service_last_change = None
        self.service_create_date = None
        self.service_bounding_box = None

        # service_provider
        self.service_provider_providername = None
        self.service_provider_url = None

        self.service_provider_responsibleparty_individualname = None
        self.service_provider_responsibleparty_positionname = None
        self.service_provider_responsibleparty_role = None

        self.service_provider_contact_hoursofservice = None
        self.service_provider_contact_contactinstructions = None
        self.service_provider_onlineresource_linkage = None

        self.service_provider_address = []
        self.service_provider_address_city = None
        self.service_provider_address_state_or_province = None
        self.service_provider_address_postalcode = []
        self.service_provider_address_country = []
        self.service_provider_address_electronicmailaddress = []

        self.service_provider_telephone_voice = []
        self.service_provider_telephone_facsimile = []

        # other
        self.linked_service_metadata = None

        # ServiceUrls:
        self.get_capabilities_uri_GET = None
        self.get_capabilities_uri_POST = None

        # wms specific
        self.get_map_uri_GET = None
        self.get_map_uri_POST = None
        self.get_feature_info_uri_GET = None
        self.get_feature_info_uri_POST = None
        self.describe_layer_uri_GET = None
        self.describe_layer_uri_POST = None
        self.get_legend_graphic_uri_GET = None
        self.get_legend_graphic_uri_POST = None
        self.get_styles_uri_GET = None
        self.get_styles_uri_POST = None

        # wfs specific
        self.describe_feature_type_uri_GET = None
        self.describe_feature_type_uri_POST = None
        self.get_feature_uri_GET = None
        self.get_feature_uri_POST = None
        self.transaction_uri_GET = None
        self.transaction_uri_POST = None
        self.lock_feature_uri_GET = None
        self.lock_feature_uri_POST = None
        self.get_feature_with_lock_uri_GET = None
        self.get_feature_with_lock_uri_POST = None
        # wms 1.1.0 specific
        self.get_gml_object_uri_GET = None
        self.get_gml_object_uri_POST = None

        # wms 2.0.0
        self.list_stored_queries_uri_GET = None
        self.list_stored_queries_uri_POST = None
        self.get_property_value_uri_GET = None
        self.get_property_value_uri_POST = None
        self.describe_stored_queries_uri_GET = None
        self.describe_stored_queries_uri_POST = None

        # csw specific uris
        self.describe_record_uri_GET = None
        self.describe_record_uri_POST = None
        self.get_records_uri_GET = None
        self.get_records_uri_POST = None
        self.get_record_by_id_uri_GET = None
        self.get_record_by_id_uri_POST = None

        self.operation_urls = [(OGCOperationEnum.GET_CAPABILITIES.value, 'get_capabilities_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_CAPABILITIES.value, 'get_capabilities_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_MAP.value, 'get_map_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_MAP.value, 'get_map_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_FEATURE_INFO.value, 'get_feature_info_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_FEATURE_INFO.value, 'get_feature_info_uri_POST', 'Post'),
                               (OGCOperationEnum.DESCRIBE_LAYER.value, 'describe_layer_uri_GET', 'Get'),
                               (OGCOperationEnum.DESCRIBE_LAYER.value, 'describe_layer_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_LEGEND_GRAPHIC.value, 'get_legend_graphic_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_LEGEND_GRAPHIC.value, 'get_legend_graphic_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_STYLES.value, 'get_styles_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_STYLES.value, 'get_styles_uri_POST', 'Post'),
                               # wfs specific
                               (OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value, 'describe_feature_type_uri_GET', 'Get'),
                               (OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value, 'describe_feature_type_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_FEATURE.value, 'get_feature_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_FEATURE.value, 'get_feature_uri_POST', 'Post'),
                               (OGCOperationEnum.TRANSACTION.value, 'transaction_uri_GET', 'Get'),
                               (OGCOperationEnum.TRANSACTION.value, 'transaction_uri_POST', 'Post'),
                               (OGCOperationEnum.LOCK_FEATURE.value, 'lock_feature_uri_GET', 'Get'),
                               (OGCOperationEnum.LOCK_FEATURE.value, 'lock_feature_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_FEATURE_WITH_LOCK.value, 'get_feature_with_lock_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_FEATURE_WITH_LOCK.value, 'get_feature_with_lock_uri_POST', 'Post'),
                               # wms 1.1.0 specific
                               (OGCOperationEnum.GET_GML_OBJECT.value, 'get_gml_object_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_GML_OBJECT.value, 'get_gml_object_uri_POST', 'Post'),
                               # wms 2.0.0
                               (OGCOperationEnum.LIST_STORED_QUERIES.value, 'list_stored_queries_uri_GET', 'Get'),
                               (OGCOperationEnum.LIST_STORED_QUERIES.value, 'list_stored_queries_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_PROPERTY_VALUE.value, 'get_property_value_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_PROPERTY_VALUE.value, 'get_property_value_uri_POST', 'Post'),
                               (OGCOperationEnum.DESCRIBE_STORED_QUERIES.value, 'describe_stored_queries_uri_GET',
                                'Get'),
                               (OGCOperationEnum.DESCRIBE_STORED_QUERIES.value, 'describe_stored_queries_uri_POST',
                                'Post'),
                               # csw specific
                               (OGCOperationEnum.DESCRIBE_RECORD.value, 'describe_record_uri_GET', 'Get'),
                               (OGCOperationEnum.DESCRIBE_RECORD.value, 'describe_record_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_RECORDS.value, 'get_records_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_RECORDS.value, 'get_records_uri_POST', 'Post'),
                               (OGCOperationEnum.GET_RECORD_BY_ID.value, 'get_record_by_id_uri_GET', 'Get'),
                               (OGCOperationEnum.GET_RECORD_BY_ID.value, 'get_record_by_id_uri_POST', 'Post')]

        self.operation_format_map = {}

    def get_capabilities(self):
        """ Start a network call to retrieve the original capabilities xml document.

        Using the connector class, this function will GET the capabilities xml document as string.
        No file will be downloaded and stored on the storage. The string will be stored in the OGCWebService instance.

        Returns:
             nothing
        """
        params = {
            "request": OGCOperationEnum.GET_CAPABILITIES.value,
            "version": self.service_version.value if self.service_version is not None else "",
            "service": (self.service_type.value if self.service_type is not None else "").upper(),
        }
        concat = "&" if self.service_connect_url[-1] != "&" else ""
        self.service_connect_url = "{}{}{}".format(self.service_connect_url, concat, urlencode(params))
        ows_connector = CommonConnector(
            url=self.service_connect_url,
            external_auth=self.external_authentification,
            connection_type=ConnectionEnum.REQUESTS
        )
        ows_connector.http_method = 'GET'
        try:
            ows_connector.load()
            if ows_connector.status_code != 200:
                raise ConnectionError(ows_connector.status_code)
        except ReadTimeout:
            raise ConnectionError(CONNECTION_TIMEOUT.format(self.service_connect_url))

        tmp = ows_connector.content.decode("UTF-8")
        # check if tmp really contains an xml file
        xml = xml_helper.parse_xml(tmp)

        if xml is None:
            raise Exception(tmp)

        self.service_capabilities_xml = tmp
        self.connect_duration = ows_connector.run_time
        self.descriptive_document_encoding = ows_connector.encoding

    @abstractmethod
    def deserialize_from_capabilities(self, metadata_only: bool = False):
        """ Converts the parsed `OGCWebService` instance to django relational db models and persists them.

        Returns:
             the django `Service` model  (:py:class:`service.models.Service`)
        """
        raise NotImplementedError('You have to implement create_from_capabilities()')

    @abstractmethod
    def get_service_metadata_from_capabilities(self, xml_obj):
        """ Parses all <Service> element information which can be found in every wms specification since 1.0.0
            and stores all the resolved information on it self.

        Args:
            xml_obj: The iterable xml object tree ()
        Returns:
            Nothing
        """
        raise NotImplementedError('You have to implement get_service_metadata_from_capabilities()')

    @abstractmethod
    def get_version_specific_metadata(self, xml_obj):
        raise NotImplementedError('You have to implement get_version_specific_metadata()')

    @abstractmethod
    def to_db(self,
              register_for_organization: Organization,
              is_update_candidate_for: Service):
        raise NotImplementedError('You have to implement to_db()')

    def get_service_metadata(self, uri: str):
        """ Parses all service related information from the linked metadata document

        This does not fill the information into the main metadata record, but creates a new one, which will be linked
        using a MetadataRelation later.

        Args:
            uri (str): The service metadata uri
        Returns:
            Nothing
        """
        iso_md = ISOMetadata(uri)
        iso_md.parse_xml()
        self.linked_service_metadata = iso_md

    def get_service_dataset_metadata(self, xml_obj):
        """ parses all MetadataUrl entities from the given xml_obj, tries to resolve them from remote and parses the
            remote found xml.

        Args:
            xml_obj: The xml etree object which is used for parsing (This could be a Capabilities document for example)
        Returns:
             Nothing
        """
        # Must parse metadata document and merge metadata into this metadata object
        elem = "//inspire_common:URL"  # for wms by default
        if self.service_type is OGCServiceEnum.WFS:
            elem = "//wfs:MetadataURL"
        service_md_link = xml_helper.try_get_text_from_xml_element(elem=elem, xml_elem=xml_obj)
        # get iso metadata xml object
        if service_md_link is None:
            # no iso metadata provided
            return
        iso_metadata = ISOMetadata(uri=service_md_link)
        iso_metadata.get_and_parse()

        # add keywords
        for keyword in iso_metadata.keywords:
            self.service_identification_keywords.append(keyword)
        # add multiple other data that can not be found in the capabilities document
        self.service_create_date = iso_metadata.date_stamp
        self.service_last_change = iso_metadata.last_change_date
        self.service_iso_md_uri = iso_metadata.uri
        self.service_file_iso_identifier = iso_metadata.file_identifier
        self.service_identification_title = iso_metadata.title
        self.service_identification_abstract = iso_metadata.abstract
        bounding_points = (
            (float(iso_metadata.bounding_box["min_x"]), float(iso_metadata.bounding_box["min_y"])),
            (float(iso_metadata.bounding_box["min_x"]), float(iso_metadata.bounding_box["max_y"])),
            (float(iso_metadata.bounding_box["max_x"]), float(iso_metadata.bounding_box["max_y"])),
            (float(iso_metadata.bounding_box["max_x"]), float(iso_metadata.bounding_box["min_y"])),
            (float(iso_metadata.bounding_box["min_x"]), float(iso_metadata.bounding_box["min_y"]))
        )
        bbox = Polygon(bounding_points)
        self.service_bounding_box = bbox


class OWSException:
    def __init__(self, exception: Exception):
        self.exception = exception
        try:
            self.text = exception.args[0]
        except IndexError:
            self.text = "None"
        try:
            self.locator = exception.args[1]
        except IndexError:
            self.locator = "None"

        self.namespace_map = {
            None: XML_NAMESPACES["ows"],
            "xsi": XML_NAMESPACES["xsi"],
        }

        self.xsi_ns = "{" + self.namespace_map["xsi"] + "}"
        self.ows_ns = "{" + self.namespace_map[None] + "}"

    def get_exception_report(self):
        """ Creates an OWSExceptionReport from a given Exception object

        Returns:
             report (str): The exception report as string
        """
        root = Element(
            "{}ExceptionReport".format(self.ows_ns),
            nsmap=self.namespace_map,
            attrib={
                "{}schemaLocation".format(self.xsi_ns): "http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd",
                "version": "1.2.0",
            }
        )
        exception_elem = xml_helper.create_subelement(
            root,
            "{}Exception".format(self.ows_ns),
            attrib={
                "exceptionCode": self.exception.__class__.__name__,
                "locator": self.locator,
            }
        )
        text_elem = xml_helper.create_subelement(
            exception_elem,
            "{}ExceptionText".format(self.ows_ns)
        )
        text_elem.text = self.text

        return xml_helper.xml_to_string(root, pretty_print=True)
