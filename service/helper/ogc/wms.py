# common classes for handling of WMS (OGC WebMapServices)
# http://www.opengeospatial.org/standards/wms
"""Common classes to handle WMS (OGC WebMapServices).

.. moduleauthor:: Armin Retterath <armin.retterath@gmail.com>

"""
import json
import uuid
from abc import abstractmethod

import time

from copy import copy

from django.contrib.gis.geos import Polygon
from django.db import transaction

from MapSkinner.settings import EXEC_TIME_PRINT
from MapSkinner import utils
from service.config import ALLOWED_SRS
from service.helper.enums import VersionTypes
from service.helper.epsg_api import EpsgApi
from service.helper.iso.isoMetadata import ISOMetadata
from service.helper.ogc.ows import OGCWebService
from service.helper.ogc.layer import OGCLayer

from service.helper import service_helper
from service.models import ServiceType, Service, Metadata, Layer, Dimension, MimeType, Keyword, ReferenceSystem, \
    MetadataRelation, MetadataOrigin
from structure.models import Organization, Group
from structure.models import User


class OGCWebMapServiceFactory:
    """ Creates the correct OGCWebMapService objects

    """
    def get_ogc_wms(self, version: VersionTypes, service_connect_url=None):
        """ Returns the correct implementation of an OGCWebMapService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebMapService
        """
        if version is VersionTypes.V_1_0_0:
            return OGCWebMapService_1_0_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_1_0:
            return OGCWebMapService_1_1_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_1_1:
            return OGCWebMapService_1_1_1(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_3_0:
            return OGCWebMapService_1_3_0(service_connect_url=service_connect_url)


class OGCWebMapService(OGCWebService):
    """Base class for OGC WebMapServices."""

    # define layers as array of OGCWebMapServiceLayer objects
    # Using None here to avoid mutable appending of infinite layers (python specific)
    # For further details read: http://effbot.org/zone/default-values.htm
    layers = None
    epsg_api = EpsgApi()

    class Meta:
        abstract = True

    def get_layer_by_identifier(self, identifier: str):
        """ Returns the layer identified by the parameter 'identifier' as OGCWebMapServiceLayer object

        Args:
            identifier (str): The identifier as string
        Returns:
             layer_obj (OGCWebMapServiceLayer): The found and parsed layer
        """
        if self.service_capabilities_xml is None:
            # load xml, might have been forgotten
            self.get_capabilities()
        layer_xml = service_helper.parse_xml(xml=self.service_capabilities_xml)
        layer_xml = service_helper.try_get_element_from_xml(xml_elem=layer_xml, elem="//Layer/Name[text()='{}']/parent::Layer".format(identifier))
        if len(layer_xml) > 0:
            layer_xml = layer_xml[0]
        else:
            return None
        return self._start_single_layer_parsing(layer_xml)

    @abstractmethod
    def create_from_capabilities(self, metadata_only: bool = False):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = service_helper.parse_xml(xml=self.service_capabilities_xml)

        start_time = time.time()
        self.get_service_metadata(xml_obj=xml_obj)
        print(EXEC_TIME_PRINT % ("service metadata", time.time() - start_time))

        start_time = time.time()
        self.get_service_iso_metadata(xml_obj=xml_obj)
        print(EXEC_TIME_PRINT % ("service iso metadata", time.time() - start_time))

        self.get_version_specific_metadata(xml_obj=xml_obj)

        if not metadata_only:
            start_time = time.time()
            self.get_layers(xml_obj=xml_obj)
            print(EXEC_TIME_PRINT % ("layer metadata", time.time() - start_time))

    def _start_single_layer_parsing(self, layer_xml):
        """ Runs the complete parsing process for a single layer

        Args:
            layer_xml: The xml element of the desired layer
        Returns:
             layer_obj (OGCWebMapServiceLayer): The layer object containing all metadata information
        """
        layer_obj = OGCWebMapServiceLayer()
        # iterate over single parsing functions -> improves maintainability
        parse_functions = [
            self.__parse_keywords,
            self.__parse_abstract,
            self.__parse_title,
            self.__parse_projection_system,
            self.__parse_lat_lon_bounding_box,
            self.__parse_bounding_box,
            self.__parse_scale_hint,
            self.__parse_queryable,
            self.__parse_opaque,
            self.__parse_cascaded,
            self.__parse_request_uris,
            self.__parse_formats,
            self.__parse_dimension,
            self.__parse_style,
            self.__parse_identifier,
        ]
        for func in parse_functions:
            func(layer=layer_xml, layer_obj=layer_obj)

        return layer_obj

    ### IDENTIFIER ###
    def __parse_identifier(self, layer, layer_obj):
        layer_obj.identifier = service_helper.try_get_text_from_xml_element(elem="./Name", xml_elem=layer)
        if layer_obj.identifier is None:
            layer_obj.identifier = service_helper.generate_name(layer_obj.capability_projection_system)

    ### KEYWORDS ###
    def __parse_keywords(self, layer, layer_obj):
        keywords = service_helper.try_get_element_from_xml(elem="./KeywordList/Keyword", xml_elem=layer)
        for keyword in keywords:
            layer_obj.capability_keywords.append(keyword.text)

    ### ABSTRACT ###
    def __parse_abstract(self, layer, layer_obj):
        layer_obj.abstract = service_helper.try_get_text_from_xml_element(elem="./Abstract", xml_elem=layer)

    ### TITLE ###
    def __parse_title(self, layer, layer_obj):
        layer_obj.title = service_helper.try_get_text_from_xml_element(elem="./Title", xml_elem=layer)

    ### SRS/CRS     PROJECTION SYSTEM ###
    @abstractmethod
    def __parse_projection_system(self, layer, layer_obj):
        srs = service_helper.try_get_element_from_xml(elem="./SRS", xml_elem=layer)
        for elem in srs:
            layer_obj.capability_projection_system.append(elem.text)

    ### BOUNDING BOX    LAT LON ###
    @abstractmethod
    def __parse_lat_lon_bounding_box(self, layer, layer_obj):
        try:
            bbox = service_helper.try_get_element_from_xml(elem="./LatLonBoundingBox", xml_elem=layer)[0]
            attrs = ["minx", "miny", "maxx", "maxy"]
            for attr in attrs:
                layer_obj.capability_bbox_lat_lon[attr] = bbox.get(attr)
        except IndexError:
            pass

    ### BOUNDING BOX ###
    def __parse_bounding_box_generic(self, layer, layer_obj, elem_name):
        try:
            bboxs = layer.xpath("./BoundingBox")
            for bbox in bboxs:
                srs = bbox.get(elem_name)
                srs_dict = {
                    "minx": "",
                    "miny": "",
                    "maxx": "",
                    "maxy": "",
                }
                attrs = ["minx", "miny", "maxx", "maxy"]
                for attr in attrs:
                    srs_dict[attr] = bbox.get(attr)
                layer_obj.capability_bbox_srs[srs] = srs_dict
        except (AttributeError, IndexError) as error:
            pass

    def __parse_bounding_box(self, layer, layer_obj):
        # switch depending on service version
        elem_name = "SRS"
        if self.service_version is VersionTypes.V_1_0_0:
            pass
        if self.service_version is VersionTypes.V_1_1_0:
            pass
        if self.service_version is VersionTypes.V_1_1_1:
            pass
        if self.service_version is VersionTypes.V_1_3_0:
            elem_name = "CRS"
        self.__parse_bounding_box_generic(layer=layer, layer_obj=layer_obj, elem_name=elem_name)

    ### SCALE HINT ###
    def __parse_scale_hint(self, layer, layer_obj):
        try:
            scales = service_helper.try_get_element_from_xml(elem="./ScaleHint", xml_elem=layer)[0]
            attrs = ["min", "max"]
            for attr in attrs:
                layer_obj.capability_scale_hint[attr] = scales.get(attr)
        except IndexError:
            pass

    ### IS QUERYABLE ###
    def __parse_queryable(self, layer, layer_obj):
            try:
                is_queryable = layer.get("queryable")
                if is_queryable is None:
                    is_queryable = False
                else:
                    is_queryable = utils.resolve_boolean_attribute_val(is_queryable)
                layer_obj.is_queryable = is_queryable
            except AttributeError:
                pass

    ### IS OPAQUE ###
    def __parse_opaque(self, layer, layer_obj):
            try:
                is_opaque = layer.get("opaque")
                if is_opaque is None:
                    is_opaque = False
                else:
                    is_opaque = utils.resolve_boolean_attribute_val(is_opaque)
                layer_obj.is_opaque = is_opaque
            except AttributeError:
                pass

    ### IS CASCADED ###
    def __parse_cascaded(self, layer, layer_obj):
            try:
                is_opaque = layer.get("cascaded")
                if is_opaque is None:
                    is_opaque = False
                else:
                    is_opaque = utils.resolve_boolean_attribute_val(is_opaque)
                layer_obj.is_cascaded = is_opaque
            except AttributeError:
                pass

    ### REQUEST URIS ###
    def __parse_request_uris(self, layer, layer_obj):
        attributes = {
            "cap": "//GetCapabilities/DCPType/HTTP/Get/OnlineResource",
            "map": "//GetMap/DCPType/HTTP/Get/OnlineResource",
            "feat": "//GetFeatureInfo/DCPType/HTTP/Get/OnlineResource",
            "desc": "//DescribeLayer/DCPType/HTTP/Get/OnlineResource",
            "leg": "//GetLegendGraphic/DCPType/HTTP/Get/OnlineResource",
            "style": "//GetStyles/DCPType/HTTP/Get/OnlineResource",
        }
        for key, val in attributes.items():
            try:
                tmp = layer.xpath(val)[0].get("{http://www.w3.org/1999/xlink}href")
                attributes[key] = tmp
            except (AttributeError, IndexError) as error:
                attributes[key] = None

        layer_obj.get_capabilities_uri = attributes.get("cap")
        layer_obj.get_map_uri = attributes.get("map")
        layer_obj.get_feature_info_uri = attributes.get("feat")
        layer_obj.describe_layer_uri = attributes.get("desc")
        layer_obj.get_legend_graphic_uri = attributes.get("leg")
        layer_obj.get_styles_uri = attributes.get("style")

    ### FORMATS ###
    @abstractmethod
    def __parse_formats(self, layer, layer_obj):
        actions = ["GetMap", "GetCapabilities", "GetFeatureInfo", "DescribeLayer", "GetLegendGraphic", "GetStyles"]
        results = {}
        for action in actions:
            try:
                results[action] = []
                format_list = layer.xpath("//" + action + "/Format")
                for format in format_list:
                    results[action].append(format.text)
            except AttributeError:
                pass
        layer_obj.format_list = results

    ### DIMENSIONS ###
    @abstractmethod
    def __parse_dimension(self, layer, layer_obj):
        dims_list = []
        try:
            dim = layer.xpath("./Dimension")[0]
            ext = layer.xpath("./Extent")[0]
            dim_dict = {
                "name": dim.get("name"),
                "units": dim.get("units"),
                "default": ext.get("default"),
                "extent": ext.text,
            }
            dims_list.append(dim_dict)
        except (IndexError, AttributeError) as error:
            pass
        layer_obj.dimension = dims_list

    ### STYLES ###
    def __parse_style(self, layer, layer_obj):
        style = service_helper.try_get_element_from_xml("./Style", layer)
        elements = {
            "name": "./Name",
            "title": "./Title",
            "width": "./LegendURL",
            "height": "./LegendURL",
            "uri": "./LegendURL/OnlineResource"
        }
        for key, val in elements.items():
            tmp = service_helper.try_get_element_from_xml(elem=val, xml_elem=style)
            try:
                elements[key] = tmp[0]
            except (IndexError, TypeError) as error:
                elements[key] = None
        elements["name"] = elements["name"].text if elements["name"] is not None else None
        elements["title"] = elements["title"].text if elements["title"] is not None else None
        elements["width"] = elements["width"].get("width") if elements["width"] is not None else None
        elements["height"] = elements["height"].get("height") if elements["height"] is not None else None
        elements["uri"] = elements["uri"].get("xlink:href") if elements["uri"] is not None else None
        layer_obj.style = elements

    def __has_iso_metadata(self, xml):
        """ Checks whether the xml element has an iso 19115 metadata record or not

        Args:
            xml: The xml etree object
        Returns:
             True if element has iso metadata, false otherwise
        """
        iso_metadata = service_helper.try_get_element_from_xml(xml_elem=xml, elem="./MetadataURL")
        return len(iso_metadata) != 0

    def __get_layers_recursive(self, layers, parent=None, position=0):
        """ Recursive Iteration over all children and subchildren.

        Creates OGCWebMapLayer objects for each xml layer and fills it with the layer content.

        Args:
            layers: An array of layers (In fact the children of the parent layer)
            parent: The parent layer. If no parent exist it means we are in the root layer
            position: The position inside the layer tree, which is more like an order number
        :return:
        """
        for layer in layers:
            # iterate over all top level layer and find their children
            layer_obj = self._start_single_layer_parsing(layer)
            layer_obj.parent = parent
            layer_obj.position = position
            if self.layers is None:
                self.layers = []

            # check for possible ISO metadata
            if self.__has_iso_metadata(layer):
                iso_metadata_xml_elements = service_helper.try_get_element_from_xml(xml_elem=layer, elem="./MetadataURL/OnlineResource")
                for iso_xml in iso_metadata_xml_elements:
                    iso_uri = service_helper.try_get_attribute_from_xml_element(xml_elem=iso_xml, attribute="{http://www.w3.org/1999/xlink}href")
                    iso_metadata = ISOMetadata(uri=iso_uri, origin="capabilities")
                    layer_obj.iso_metadata.append(iso_metadata)

            self.layers.append(layer_obj)
            sublayers = service_helper.try_get_element_from_xml(elem="./Layer", xml_elem=layer)
            if parent is not None:
                parent.child_layer.append(layer_obj)
            position += 1
            self.__get_layers_recursive(layers=sublayers, parent=layer_obj, position=position)


    def get_layers(self, xml_obj):
        """ Parses all layers of a service and creates objects for it.

        Uses recursion on the inside to get all children.

        Args:
            xml_obj: The iterable xml tree
        Returns:
             nothing
        """
        # get most upper parent layer, which normally lives directly in <Capability>
        layers = xml_obj.xpath("//Capability/Layer")
        self.__get_layers_recursive(layers)

    def get_service_metadata(self, xml_obj):
        """ This private function holds the main parsable elements which are part of every wms specification starting at 1.0.0
        Args:
            xml_obj: The iterable xml object tree
        Returns:
            Nothing
        """
        # Since it may be possible that data providers do not put information where they have to be, we need to
        # build these ugly try catches and always check for list structures where lists could happen
        try:
            self.service_identification_abstract = xml_obj.xpath("//Service/Abstract")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_identification_title = xml_obj.xpath("//Service/Title")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_identification_fees = xml_obj.xpath("//Service/Fees")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_identification_accessconstraints = xml_obj.xpath("//Service/AccessConstraints")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_providername = \
            xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactOrganization")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_url = xml_obj.xpath("//AuthorityURL")[0].get("xlink:href")
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_contact_contactinstructions = xml_obj.xpath("//Service/ContactInformation")[0]
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_responsibleparty_individualname = \
            xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactPerson")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_responsibleparty_positionname = \
            xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactPosition")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_telephone_voice = \
            xml_obj.xpath("//Service/ContactInformation/ContactVoiceTelephone")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_telephone_facsimile = \
            xml_obj.xpath("//Service/ContactInformation/ContactFacsimileTelephone")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_electronicmailaddress = \
            xml_obj.xpath("//Service/ContactInformation/ContactElectronicMailAddress")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            keywords = xml_obj.xpath("//Service/KeywordList/Keyword")
            kw = []
            for keyword in keywords:
                kw.append(keyword.text)
            self.service_identification_keywords = kw
        except (IndexError, AttributeError) as error:
            pass
        try:
            elements = xml_obj.xpath("//Service/OnlineResource")
            ors = []
            for element in elements:
                ors.append(element.get("{http://www.w3.org/1999/xlink}href"))
            self.service_provider_onlineresource_linkage = ors
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_country = \
            xml_obj.xpath("//Service/ContactInformation/ContactAddress/Country")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_postalcode = \
            xml_obj.xpath("//Service/ContactInformation/ContactAddress/PostCode")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_city = xml_obj.xpath("//Service/ContactInformation/ContactAddress/City")[
                0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_state_or_province = \
            xml_obj.xpath("//Service/ContactInformation/ContactAddress/StateOrProvince")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address = xml_obj.xpath("//Service/ContactInformation/ContactAddress/Address")[
                0].text
        except (IndexError, AttributeError) as error:
            pass

    @transaction.atomic
    def __create_layer_model_instance(self, layers: list, service_type: ServiceType, wms: Service, creator: Group, publisher: Organization,
                         published_for: Organization, root_md: Metadata, user: User, contact, parent=None):
        """ Iterates over all layers given by the service and persist them, including additional data like metadata and so on.

        Args:
            layers (list): A list of layers
            service_type (ServiceType): The type of the service this function has to deal with
            wms (Service): The root or parent service which holds all these layers
            creator (Group): The group that started the registration process
            publisher (Organization): The organization that publishes the service
            published_for (Organization): The organization for which the first organization publishes this data (e.g. 'in the name of')
            root_md (Metadata): The metadata of the root service (parameter 'wms')
        Returns:
        """

        # iterate over all layers
        for layer_obj in layers:
            metadata = Metadata()
            metadata.title = layer_obj.title
            metadata.uuid = uuid.uuid4()
            metadata.abstract = layer_obj.abstract
            metadata.online_resource = root_md.online_resource
            metadata.original_uri = root_md.original_uri

            metadata.contact = contact
            metadata.access_constraints = root_md.access_constraints
            metadata.is_active = False
            metadata.created_by = creator

            # handle keywords of this layer
            for kw in layer_obj.capability_keywords:
                keyword = Keyword.objects.get_or_create(keyword=kw)[0]
                metadata.keywords_list.append(keyword)
                #metadata.keywords.add(keyword)

            # handle reference systems
            for sys in layer_obj.capability_projection_system:
                parts = self.epsg_api.get_subelements(sys)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                ref_sys = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                metadata.reference_system_list.append(ref_sys)
                #metadata.reference_system.add(ref_sys)

            layer = Layer()
            layer.uuid = uuid.uuid4()
            layer.metadata = metadata
            layer.identifier = layer_obj.identifier
            layer.servicetype = service_type
            layer.position = layer_obj.position
            layer.parent_layer = parent
            if layer.parent_layer is not None:
                layer.parent_layer.children_list.append(layer)
            layer.is_queryable = layer_obj.is_queryable
            layer.is_cascaded = layer_obj.is_cascaded
            layer.registered_by = creator
            layer.is_opaque = layer_obj.is_opaque
            layer.scale_min = layer_obj.capability_scale_hint.get("min")
            layer.scale_max = layer_obj.capability_scale_hint.get("max")
            # create bounding box polygon
            bounding_points = (
                (float(layer_obj.capability_bbox_lat_lon["minx"]), float(layer_obj.capability_bbox_lat_lon["miny"])),
                (float(layer_obj.capability_bbox_lat_lon["minx"]), float(layer_obj.capability_bbox_lat_lon["maxy"])),
                (float(layer_obj.capability_bbox_lat_lon["maxx"]), float(layer_obj.capability_bbox_lat_lon["maxy"])),
                (float(layer_obj.capability_bbox_lat_lon["maxx"]), float(layer_obj.capability_bbox_lat_lon["miny"])),
                (float(layer_obj.capability_bbox_lat_lon["minx"]), float(layer_obj.capability_bbox_lat_lon["miny"]))
            )
            layer.bbox_lat_lon = Polygon(bounding_points)

            layer.created_by = creator
            layer.published_for = published_for
            layer.published_by = publisher
            layer.parent_service = wms
            layer.get_styles_uri = layer_obj.get_styles_uri
            layer.get_legend_graphic_uri = layer_obj.get_legend_graphic_uri
            layer.get_feature_info_uri = layer_obj.get_feature_info_uri
            layer.get_map_uri = layer_obj.get_map_uri
            layer.describe_layer_uri = layer_obj.describe_layer_uri
            layer.get_capabilities_uri = layer_obj.get_capabilities_uri

            layer.iso_metadata = layer_obj.iso_metadata

            if layer_obj.dimension is not None and len(layer_obj.dimension) > 0:
                # ToDo: Rework dimension persisting! Currently simply ignore it...
                pass
                # for dimension in layer_obj.dimension:
                #     dim = Dimension()
                #     # dim.layer = layer
                #     dim.name = layer_obj.dimension.get("name")
                #     dim.units = layer_obj.dimension.get("units")
                #     dim.default = layer_obj.dimension.get("default")
                #     dim.extent = layer_obj.dimension.get("extent")
                #     # ToDo: Refine for inherited and nearest_value and so on
                #     layer.dimension = dim
                #     #dim.save()

            if wms.root_layer is None:
                # no root layer set yet
                wms.root_layer = layer

            #layer.save()

            # iterate over all available mime types and actions
            for action, format_list in layer_obj.format_list.items():
                for _format in format_list:
                    service_to_format = MimeType.objects.get_or_create(
                        action=action,
                        mime_type=_format,
                        created_by=creator
                    )[0]
                    #layer.formats.add(service_to_format)
                    layer.formats_list.append(service_to_format)

            if len(layer_obj.child_layer) > 0:
                parent_layer = copy(layer)
                self.__create_layer_model_instance(layers=layer_obj.child_layer, service_type=service_type, wms=wms, creator=creator, root_md=root_md,
                         publisher=publisher, published_for=published_for, parent=parent_layer, user=user, contact=contact)

    @transaction.atomic
    def create_service_model_instance(self, user: User, register_group, register_for_organization):
        """ Persists the web map service and all of its related content and data

        Args:
            user (User): The action performing user
        Returns:
             service (Service): Service instance, contains all information, ready for persisting!

        """
        orga_published_for = register_for_organization
        orga_publisher = user.organization

        group = register_group

        # fill objects
        service_type = ServiceType.objects.get_or_create(
            name=self.service_type.value,
            version=self.service_version.value
        )[0]
        # metadata
        metadata = Metadata()
        if self.service_file_identifier is None:
            self.service_file_identifier = uuid.uuid4()
        metadata.uuid = self.service_file_identifier
        metadata.title = self.service_identification_title
        metadata.abstract = self.service_identification_abstract
        metadata.online_resource = ",".join(self.service_provider_onlineresource_linkage)
        metadata.original_uri = self.service_connect_url
        metadata.access_constraints = self.service_identification_accessconstraints
        metadata.fees = self.service_identification_fees
        metadata.bounding_geometry = self.service_bounding_box
        ## keywords
        for kw in self.service_identification_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            metadata.keywords_list.append(keyword)
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
        metadata.contact = contact
        ## other
        metadata.is_active = False
        metadata.created_by = group
        #metadata.save()

        service = Service()
        service.availability = 0.0
        service.is_available = False
        service.servicetype = service_type
        service.published_for = orga_published_for
        service.published_by = orga_publisher
        service.created_by = group
        service.metadata = metadata
        service.is_root = True
        #service.save()

        root_layer = self.layers[0]

        self.__create_layer_model_instance(layers=[root_layer], service_type=service_type, wms=service, creator=group, root_md=copy(metadata),
                         publisher=orga_publisher, published_for=orga_published_for, contact=contact, user=user)
        return service

    @transaction.atomic
    def persist_service_model(self, service):
        """ Persist the service model object

        Returns:
             Nothing
        """
        # save metadata
        md = service.metadata
        md.save()
        # metadata keywords
        for kw in md.keywords_list:
            md.keywords.add(kw)
        service.metadata = md
        # save parent service
        service.save()
        # save all containing layers
        if service.root_layer is not None:
            self.__persist_child_layers([service.root_layer], service)

    @transaction.atomic
    def __persist_child_layers(self, layers, parent_service, parent_layer=None):
        """ Persist all layer children

        Args:
            parent_layer:
        Returns:
             Nothing
        """
        for layer in layers:
            md = layer.metadata
            md.save()
            for iso_md in layer.iso_metadata:
                iso_md = iso_md.get_db_model()
                metadata_relation = MetadataRelation()
                metadata_relation.metadata_1 = md
                metadata_relation.metadata_2 = iso_md
                metadata_relation.origin = MetadataOrigin.objects.get_or_create(
                    name=iso_md.origin
                )[0]
                metadata_relation.save()
                md.related_metadata.add(metadata_relation)

            layer.metadata = md

            # handle keywords of this layer
            for kw in layer.metadata.keywords_list:
                layer.metadata.keywords.add(kw)

            # handle reference systems
            for sys in layer.metadata.reference_system_list:
                layer.metadata.reference_system.add(sys)

            if layer.dimension is not None:
                dim = layer.dimension
                dim.save()
                layer.dimension = dim

            layer.parent_layer = parent_layer
            layer.parent_service = parent_service
            layer.save()

            # iterate over all available mime types and actions
            for _format in layer.formats_list:
                layer.formats.add(_format)

            if len(layer.children_list) > 0:
                self.__persist_child_layers(layer.children_list, parent_service, layer)


class OGCWebMapServiceLayer(OGCLayer):
    """ The OGCWebMapServiceLayer class

    """




class OGCWebMapService_1_0_0(OGCWebMapService):
    """ The WMS class for standard version 1.0.0

    """
    def __init__(self, service_connect_url):
        super().__init__(service_connect_url=service_connect_url)
        self.service_version = VersionTypes.V_1_0_0

    def __parse_formats(self, layer, layer_obj):
        # ToDo: Find wms 1.0.0 for testing!!!!
        actions = ["Map", "Capabilities", "FeatureInfo"]
        results = {}
        for action in actions:
            try:
                results[action] = []
                format_list = layer.xpath("//Request/" + action + "/Format").getchildren()
                for format in format_list:
                    results[action].append(format.text)
            except AttributeError:
                pass
        layer_obj.format_list = results

    def get_version_specific_metadata(self, xml_obj):
        pass


class OGCWebMapService_1_1_0(OGCWebMapService):
    """ The WMS class for standard version 1.1.0

    """
    def __init__(self, service_connect_url):
        super().__init__(service_connect_url=service_connect_url)
        self.service_version = VersionTypes.V_1_1_0

    def get_version_specific_metadata(self, xml_obj):
        pass


class OGCWebMapService_1_1_1(OGCWebMapService):
    """ The WMS class for standard version 1.1.1

    """
    def __init__(self, service_connect_url=None):
        super().__init__(service_connect_url=service_connect_url)
        self.service_version = VersionTypes.V_1_1_1

    def get_version_specific_metadata(self, xml_obj):
        pass



class OGCWebMapService_1_3_0(OGCWebMapService):
    """ The WMS class for standard version 1.3.0

    """

    def __init__(self, service_connect_url):
        super().__init__(service_connect_url=service_connect_url)
        self.service_version = VersionTypes.V_1_3_0
        self.layer_limit = None
        self.max_width = None
        self.max_height = None

    def __parse_lat_lon_bounding_box(self, layer, layer_obj):
        try:
            bbox = service_helper.try_get_element_from_xml("./EX_GeographicBoundingBox", layer)[0]
            attrs = {
                "westBoundLongitude": "minx",
                "eastBoundLongitude": "maxx",
                "southBoundLatitude": "miny",
                "northBoundLatitude": "maxy",
            }
            for key, val in attrs.items():
                layer_obj.capability_bbox_lat_lon[val] = bbox.get(key)
        except IndexError:
            pass

    def __parse_projection_system(self, layer, layer_obj):
        crs = service_helper.try_get_element_from_xml("./CRS", layer)
        for elem in crs:
            layer_obj.capability_projection_system.append(elem.text)

    def __parse_dimension(self, layer, layer_obj):
        dims_list = []
        try:
            dims = layer.xpath("./Dimension")
            for dim in dims:
                dim_dict = {
                    "name": dim.get("name"),
                    "units": dim.get("units"),
                    "default": dim.get("default"),
                    "extent": dim.text,
                    "nearestValue": dim.get("nearestValue"),
                }
                dims_list.append(dim_dict)
        except (IndexError, AttributeError) as error:
            pass
        layer_obj.dimension = dims_list

    def get_version_specific_service_metadata(self, xml_obj):
        # layer limit is new
        try:
            layer_limit = xml_obj.xpath("//LayerLimit")[0].text
            self.layer_limit = layer_limit
        except (IndexError, AttributeError) as error:
            pass
        # max height and width is new
        try:
            max_width = xml_obj.xpath("//MaxWidth")[0].text
            self.max_width = max_width
        except (IndexError, AttributeError) as error:
            pass
        try:
            max_height = xml_obj.xpath("//MaxHeight")[0].text
            self.max_height = max_height
        except (IndexError, AttributeError) as error:
            pass
        self.get_layers(xml_obj=xml_obj)