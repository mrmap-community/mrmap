# common classes for handling of WMS (OGC WebMapServices)
# http://www.opengeospatial.org/standards/wms
"""Common classes to handle WMS (OGC WebMapServices).

.. moduleauthor:: Armin Retterath <armin.retterath@gmail.com>

"""
import uuid
from abc import abstractmethod

import time

from copy import copy
from threading import Thread

from celery import Task
from django.contrib.gis.geos import Polygon
from django.db import transaction

from MapSkinner.settings import EXEC_TIME_PRINT, MD_TYPE_LAYER, MD_TYPE_SERVICE, MULTITHREADING_THRESHOLD, \
    PROGRESS_STATUS_AFTER_PARSING, XML_NAMESPACES
from MapSkinner import utils
from MapSkinner.utils import execute_threads, sha256
from service.config import ALLOWED_SRS
from service.helper.enums import VersionTypes
from service.helper.epsg_api import EpsgApi
from service.helper.iso.isoMetadata import ISOMetadata
from service.helper.ogc.ows import OGCWebService
from service.helper.ogc.layer import OGCLayer

from service.helper import xml_helper, task_helper
from service.models import ServiceType, Service, Metadata, Layer, MimeType, Keyword, ReferenceSystem, \
    MetadataRelation, MetadataOrigin, MetadataType
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

    def get_parser_prefix(self):
        prefix = ""
        if isinstance(self, OGCWebMapService_1_3_0) or isinstance(self, OGCWebMapService_1_1_0):
            prefix = "wms:"
        return prefix

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
        layer_xml = xml_helper.parse_xml(xml=self.service_capabilities_xml)
        layer_xml = xml_helper.try_get_element_from_xml(xml_elem=layer_xml, elem="//Layer/Name[text()='{}']/parent::Layer".format(identifier))
        if len(layer_xml) > 0:
            layer_xml = layer_xml[0]
        else:
            return None
        return self._start_single_layer_parsing(layer_xml)

    @abstractmethod
    def create_from_capabilities(self, metadata_only: bool = False, async_task: Task = None):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)

        start_time = time.time()
        self.get_service_metadata(xml_obj=xml_obj, async_task=async_task)
        print(EXEC_TIME_PRINT % ("service metadata", time.time() - start_time))

        start_time = time.time()
        self.get_service_iso_metadata(xml_obj=xml_obj)
        print(EXEC_TIME_PRINT % ("service iso metadata", time.time() - start_time))

        self.get_version_specific_metadata(xml_obj=xml_obj)

        if not metadata_only:
            start_time = time.time()
            self.get_layers(xml_obj=xml_obj, async_task=async_task)
            print(EXEC_TIME_PRINT % ("layer metadata", time.time() - start_time))

    ### ISO METADATA ###
    def parse_iso_md(self, layer, layer_obj):
        # check for possible ISO metadata
        if self.has_iso_metadata(layer):
            iso_metadata_xml_elements = xml_helper.try_get_element_from_xml(xml_elem=layer,
                                                                            elem="./{}MetadataURL/{}OnlineResource".format(
                                                                                self.get_parser_prefix(), self.get_parser_prefix()
                                                                            ))
            for iso_xml in iso_metadata_xml_elements:
                iso_uri = xml_helper.try_get_attribute_from_xml_element(xml_elem=iso_xml,
                                                                        attribute="{http://www.w3.org/1999/xlink}href")
                try:
                    iso_metadata = ISOMetadata(uri=iso_uri, origin="capabilities")
                except Exception:
                    # there are iso metadatas that have been filled wrongly -> if so we will drop them
                    continue
                layer_obj.iso_metadata.append(iso_metadata)

    ### IDENTIFIER ###
    def parse_identifier(self, layer, layer_obj):
        layer_obj.identifier = xml_helper.try_get_text_from_xml_element(elem="./{}Name".format(self.get_parser_prefix()), xml_elem=layer)
        if layer_obj.identifier is None:
            u = str(uuid.uuid4())
            layer_obj.identifier = sha256(u)

    ### KEYWORDS ###
    def parse_keywords(self, layer, layer_obj):
        keywords = xml_helper.try_get_element_from_xml(elem="./{}KeywordList/{}Keyword".format(self.get_parser_prefix(), self.get_parser_prefix()), xml_elem=layer)
        for keyword in keywords:
            layer_obj.capability_keywords.append(keyword.text)

    ### ABSTRACT ###
    def parse_abstract(self, layer, layer_obj):
        layer_obj.abstract = xml_helper.try_get_text_from_xml_element(elem="./{}Abstract".format(self.get_parser_prefix()), xml_elem=layer)

    ### TITLE ###
    def parse_title(self, layer, layer_obj):
        layer_obj.title = xml_helper.try_get_text_from_xml_element(elem="./{}Title".format(self.get_parser_prefix()), xml_elem=layer)

    ### SRS/CRS     PROJECTION SYSTEM ###
    def parse_projection_system(self, layer, layer_obj):
        srs = xml_helper.try_get_element_from_xml(elem="./{}SRS".format(self.get_parser_prefix()), xml_elem=layer)
        for elem in srs:
            layer_obj.capability_projection_system.append(elem.text)

    ### BOUNDING BOX    LAT LON ###
    def parse_lat_lon_bounding_box(self, layer, layer_obj):
        try:
            bbox = xml_helper.try_get_element_from_xml(elem="./{}LatLonBoundingBox".format(self.get_parser_prefix()), xml_elem=layer)[0]
            attrs = ["minx", "miny", "maxx", "maxy"]
            for attr in attrs:
                val = bbox.get(attr, 0)
                if val is None:
                    val = 0
                layer_obj.capability_bbox_lat_lon[attr] = val
        except IndexError:
            pass

    ### BOUNDING BOX ###
    def parse_bounding_box_generic(self, layer, layer_obj, elem_name):
        bboxs = xml_helper.try_get_element_from_xml(elem="./BoundingBox", xml_elem=layer)
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

    def parse_bounding_box(self, layer, layer_obj):
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
        self.parse_bounding_box_generic(layer=layer, layer_obj=layer_obj, elem_name=elem_name)

    ### SCALE HINT ###
    def parse_scale_hint(self, layer, layer_obj):
        try:
            scales = xml_helper.try_get_element_from_xml(elem="./{}ScaleHint".format(self.get_parser_prefix()), xml_elem=layer)[0]
            attrs = ["min", "max"]
            for attr in attrs:
                layer_obj.capability_scale_hint[attr] = scales.get(attr)
        except IndexError:
            pass

    ### IS QUERYABLE ###
    def parse_queryable(self, layer, layer_obj):
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
    def parse_opaque(self, layer, layer_obj):
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
    def parse_cascaded(self, layer, layer_obj):
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
    def parse_request_uris(self, layer, layer_obj):
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
    def parse_formats(self, layer, layer_obj):
        actions = ["GetMap", "GetCapabilities", "GetFeatureInfo", "DescribeLayer", "GetLegendGraphic", "GetStyles"]
        results = {}
        for action in actions:
            try:
                results[action] = []
                format_list = xml_helper.try_get_element_from_xml(elem="//{}/{}Format".format(action, self.get_parser_prefix()), xml_elem=layer)
                for format in format_list:
                    results[action].append(format.text)
            except AttributeError:
                pass
        layer_obj.format_list = results

    ### DIMENSIONS ###
    def parse_dimension(self, layer, layer_obj):
        dims_list = []
        try:
            dim = xml_helper.try_get_single_element_from_xml(elem="./{}Dimension".format(self.get_parser_prefix()), xml_elem=layer)
            ext = xml_helper.try_get_single_element_from_xml(elem="./{}Extent".format(self.get_parser_prefix()), xml_elem=layer)
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
    def parse_style(self, layer, layer_obj):
        parser_prefix = self.get_parser_prefix()
        style = xml_helper.try_get_element_from_xml("./{}Style".format(parser_prefix), layer)
        elements = {
            "name": "./Name".format(parser_prefix),
            "title": "./Title".format(parser_prefix),
            "width": "./LegendURL".format(parser_prefix),
            "height": "./LegendURL".format(parser_prefix),
            "uri": "./{}LegendURL/{}OnlineResource".format(parser_prefix, parser_prefix)
        }
        for key, val in elements.items():
            tmp = xml_helper.try_get_element_from_xml(elem=val, xml_elem=style)
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
            self.parse_keywords,
            self.parse_abstract,
            self.parse_title,
            self.parse_projection_system,
            self.parse_lat_lon_bounding_box,
            self.parse_bounding_box,
            self.parse_scale_hint,
            self.parse_queryable,
            self.parse_opaque,
            self.parse_cascaded,
            self.parse_request_uris,
            self.parse_formats,
            self.parse_dimension,
            self.parse_style,
            self.parse_identifier,
            self.parse_iso_md,
        ]
        for func in parse_functions:
            func(layer=layer_xml, layer_obj=layer_obj)

        return layer_obj


    def _parse_single_layer(self, layer, parent, position, step_size: float = None, async_task: Task = None):
        """ Parses data from an xml <Layer> element into the OGCWebMapLayer object.

        Runs recursive through own children for further parsing

        Args:
            layer: The layer xml element
            parent: The parent OGCWebMapLayer object
            position: The current position of this layer object in relation to it's siblings
        Returns:
            nothing
        """
        if step_size is not None and async_task is not None:
            task_helper.update_progress_by_step(async_task, step_size)

        # iterate over all top level layer and find their children
        layer_obj = self._start_single_layer_parsing(layer)
        layer_obj.parent = parent
        layer_obj.position = position
        if self.layers is None:
            self.layers = []
        self.layers.append(layer_obj)
        sublayers = xml_helper.try_get_element_from_xml(elem="./{}Layer".format(self.get_parser_prefix()), xml_elem=layer)
        if parent is not None:
            parent.child_layer.append(layer_obj)
        position += 1

        self.get_layers_recursive(layers=sublayers, parent=layer_obj, step_size=step_size, async_task=async_task)


    def get_layers_recursive(self, layers, parent=None, position=0, step_size: float = None, async_task: Task = None):
        """ Recursive Iteration over all children and subchildren.

        Creates OGCWebMapLayer objects for each xml layer and fills it with the layer content.

        Args:
            layers: An array of layers (In fact the children of the parent layer)
            parent: The parent layer. If no parent exist it means we are in the root layer
            position: The position inside the layer tree, which is more like an order number
        :return:
        """

        # decide whether to user multithreading or iterative approach
        if len(layers) > MULTITHREADING_THRESHOLD:
            thread_list = []
            for layer in layers:
                thread_list.append(
                    Thread(target=self._parse_single_layer,
                           args=(layer, parent, position))
                )
                position += 1
            execute_threads(thread_list)
        else:
            for layer in layers:
                self._parse_single_layer(layer, parent, position, step_size=step_size, async_task=async_task)
                position += 1



    def get_layers(self, xml_obj, async_task: Task = None):
        """ Parses all layers of a service and creates OGCWebMapLayer objects from each.

        Uses recursion on the inside to get all children.

        Args:
            xml_obj: The iterable xml tree
        Returns:
             nothing
        """
        # get most upper parent layer, which normally lives directly in <Capability>
        layers = xml_helper.try_get_element_from_xml(elem="//{}Capability/{}Layer".format(self.get_parser_prefix(), self.get_parser_prefix()), xml_elem=xml_obj)
        total_layers = xml_helper.try_get_element_from_xml(elem="//{}Layer".format(self.get_parser_prefix()), xml_elem=xml_obj)

        # calculate the step size for an async call
        # 55 is the diff from the last process update (10) to the next static one (65)
        len_layers = len(total_layers)
        step_size = float(PROGRESS_STATUS_AFTER_PARSING / len_layers)
        print("Total number of layers: {}. Step size: {}".format(len_layers, step_size))

        self.get_layers_recursive(layers, step_size=step_size, async_task=async_task)

    def get_service_metadata(self, xml_obj, async_task: Task = None):
        """ Parses all <Service> information which can be found in every wms specification since 1.0.0

        Args:
            xml_obj: The iterable xml object tree
        Returns:
            Nothing
        """
        parser_prefix = self.get_parser_prefix()

        self.service_file_identifier = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}Name".format(parser_prefix, parser_prefix))
        self.service_identification_abstract = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}Abstract".format(parser_prefix, parser_prefix))
        self.service_identification_title = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}Title".format(parser_prefix, parser_prefix))

        #if async_task is not None:
        #    task_helper.update_service_description(async_task, self.service_identification_title)

        self.service_identification_fees = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}Fees".format(parser_prefix, parser_prefix))
        self.service_identification_accessconstraints = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}AccessConstraints".format(parser_prefix, parser_prefix))
        self.service_provider_providername = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactPersonPrimary/{}ContactOrganization".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix
        ))
        self.service_provider_url = xml_helper.try_get_attribute_from_xml_element(elem="//{}AuthorityURL".format(parser_prefix), xml_elem=xml_obj, attribute="{http://www.w3.org/1999/xlink}href")
        self.service_provider_contact_contactinstructions = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//{}Service/{}ContactInformation".format(parser_prefix, parser_prefix))
        self.service_provider_responsibleparty_individualname = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactPersonPrimary/{}ContactPerson".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix
        ))
        self.service_provider_responsibleparty_positionname = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactPersonPrimary/{}ContactPosition".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix
        ))
        self.service_provider_telephone_voice = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactVoiceTelephone".format(
            parser_prefix,
            parser_prefix,
            parser_prefix
        ))
        self.service_provider_telephone_facsimile = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactFacsimileTelephone".format(
            parser_prefix,
            parser_prefix,
            parser_prefix
        ))
        self.service_provider_address_electronicmailaddress = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactElectronicMailAddress".format(
            parser_prefix,
            parser_prefix,
            parser_prefix
        ))

        keywords = xml_helper.try_get_element_from_xml("//{}Service/{}KeywordList/{}Keyword".format(
            parser_prefix,
            parser_prefix,
            parser_prefix
        ), xml_obj)
        kw = []
        for keyword in keywords:
            kw.append(keyword.text)
        self.service_identification_keywords = kw

        elements = xml_helper.try_get_element_from_xml("//{}Service/{}OnlineResource".format(
            parser_prefix,
            parser_prefix
        ), xml_obj)
        ors = []
        for element in elements:
            ors.append(element.get("{http://www.w3.org/1999/xlink}href"))
        self.service_provider_onlineresource_linkage = ors

        self.service_provider_address_country = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactAddress/{}Country".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix,
        ))
        self.service_provider_address_postalcode = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactAddress/{}PostCode".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix,
        ))
        self.service_provider_address_city = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactAddress/{}City".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix,
        ))
        self.service_provider_address_state_or_province = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactAddress/{}StateOrProvince".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix,
        ))
        self.service_provider_address = xml_helper.try_get_text_from_xml_element(xml_obj, "//{}Service/{}ContactInformation/{}ContactAddress/{}Address".format(
            parser_prefix,
            parser_prefix,
            parser_prefix,
            parser_prefix,
        ))


    def __create_single_layer_model_instance(self, layer_obj, layers: list, service_type: ServiceType, wms: Service, creator: Group, publisher: Organization,
                         published_for: Organization, root_md: Metadata, user: User, contact, parent=None):
        """ Transforms a OGCWebMapLayer object to Layer model (models.py)

        Args:
            layer_obj (OGCWebMapServiceLayer): The OGCWebMapLayer object which holds all data
            layers (list): A list of layers
            service_type (ServiceType): The type of the service this function has to deal with
            wms (Service): The root or parent service which holds all these layers
            creator (Group): The group that started the registration process
            publisher (Organization): The organization that publishes the service
            published_for (Organization): The organization for which the first organization publishes this data (e.g. 'in the name of')
            root_md (Metadata): The metadata of the root service (parameter 'wms')
            user (User): The performing user
            contact (Contact): The contact object (Organization)
            parent: The parent layer object to this layer
        Returns:
            nothing
        """
        metadata = Metadata()
        md_type = MetadataType(type=MD_TYPE_LAYER)
        metadata.metadata_type = md_type
        metadata.title = layer_obj.title
        metadata.uuid = uuid.uuid4()
        metadata.abstract = layer_obj.abstract
        metadata.online_resource = root_md.online_resource
        metadata.original_uri = root_md.original_uri
        metadata.identifier = layer_obj.identifier
        metadata.contact = contact
        metadata.access_constraints = root_md.access_constraints
        metadata.is_active = False
        metadata.created_by = creator

        # handle keywords of this layer
        for kw in layer_obj.capability_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            #keyword = Keyword(keyword=kw)
            metadata.keywords_list.append(keyword)

        # handle reference systems
        for sys in layer_obj.capability_projection_system:
            parts = self.epsg_api.get_subelements(sys)
            # check if this srs is allowed for us. If not, skip it!
            if parts.get("code") not in ALLOWED_SRS:
                continue
            # ref_sys = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            ref_sys = ReferenceSystem(code=parts.get("code"), prefix=parts.get("prefix"))
            metadata.reference_system_list.append(ref_sys)

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

        # iterate over all available mime types and actions
        for action, format_list in layer_obj.format_list.items():
            for _format in format_list:
                #service_to_format = MimeType.objects.get_or_create(
                #    action=action,
                #    mime_type=_format,
                #    created_by=creator
                #)[0]
                service_to_format = MimeType(
                    action=action,
                    mime_type=_format,
                    created_by=creator
                )
                layer.formats_list.append(service_to_format)
        if len(layer_obj.child_layer) > 0:
            parent_layer = copy(layer)
            self.__create_layer_model_instance(layers=layer_obj.child_layer, service_type=service_type, wms=wms, creator=creator, root_md=root_md,
                     publisher=publisher, published_for=published_for, parent=parent_layer, user=user, contact=contact)


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
            user (User): The performing user
            contact (Contact): The contact object (Organization)
            parent: The parent layer object to this layer
        Returns:
            nothing
        """
        # iterate over all layers
        # There were attempts to implement a multithreaded approach in here but due to the problem of n-depth of layer hierarchy
        # there was no working solution so far which worked.

        for layer_obj in layers:
            self.__create_single_layer_model_instance(
                layer_obj,
                layers,
                service_type,
                wms,
                creator,
                publisher,
                published_for,
                root_md,
                user,
                contact,
                parent,
            )

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
        md_type = MetadataType.objects.get_or_create(type=MD_TYPE_SERVICE)[0]
        metadata.metadata_type = md_type
        if self.service_file_iso_identifier is None:
            # there was no file identifier found -> we create a new
            self.service_file_iso_identifier = uuid.uuid4()
        metadata.uuid = self.service_file_iso_identifier
        metadata.title = self.service_identification_title
        metadata.abstract = self.service_identification_abstract
        metadata.online_resource = ",".join(self.service_provider_onlineresource_linkage)
        metadata.original_uri = self.service_connect_url
        metadata.access_constraints = self.service_identification_accessconstraints
        metadata.fees = self.service_identification_fees
        metadata.bounding_geometry = self.service_bounding_box
        metadata.identifier = self.service_file_identifier
        # keywords
        for kw in self.service_identification_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            metadata.keywords_list.append(keyword)
        # contact
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
        # other
        metadata.is_active = False
        metadata.created_by = group

        service = Service()
        service.availability = 0.0
        service.is_available = False
        service.servicetype = service_type
        service.published_for = orga_published_for
        service.published_by = orga_publisher
        service.created_by = group
        service.metadata = metadata
        service.is_root = True

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

        Everything that has just been constructed will get a database record

        Args:
            parent_layer:
        Returns:
             Nothing
        """
        for layer in layers:
            md = layer.metadata
            md_type = md.metadata_type
            md_type = MetadataType.objects.get_or_create(type=md_type.type)[0]
            md.metadata_type = md_type
            md.save()
            for iso_md in layer.iso_metadata:
                iso_md = iso_md.to_db_model()
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
                #kw = Keyword.objects.get_or_create(keyword=kw.keyword)[0]
                layer.metadata.keywords.add(kw)

            # handle reference systems
            for sys in layer.metadata.reference_system_list:
                sys = ReferenceSystem.objects.get_or_create(code=sys.code, prefix=sys.prefix)[0]
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
                _format = MimeType.objects.get_or_create(
                    action=_format.action,
                    mime_type=_format.mime_type,
                )[0]
                layer.formats.add(_format)

            layer_children_list = layer.children_list
            if len(layer_children_list) > 0:
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

        XML_NAMESPACES["default"] = XML_NAMESPACES["wms"]

    def parse_lat_lon_bounding_box(self, layer, layer_obj):
        """ Version specific implementation of the bounding box parsing

        Args:
            layer: The xml element which holds the layer info (parsing from)
            layer_obj: The backend model which holds the layer data (parsing to)
        Returns:
             nothing
        """
        try:
            bbox = xml_helper.try_get_element_from_xml("./{}EX_GeographicBoundingBox".format(self.get_parser_prefix()), layer)[0]
            attrs = {
                "westBoundLongitude": "minx",
                "eastBoundLongitude": "maxx",
                "southBoundLatitude": "miny",
                "northBoundLatitude": "maxy",
            }
            for key, val in attrs.items():
                tmp = xml_helper.try_get_text_from_xml_element(xml_elem=bbox, elem="./{}{}".format(self.get_parser_prefix(), key))
                if tmp is None:
                    tmp = 0
                layer_obj.capability_bbox_lat_lon[val] = tmp
        except IndexError:
            pass

    def parse_projection_system(self, layer, layer_obj):
        """ Version specific implementation of the projection system parsing

        Args:
            layer: The xml element which holds the layer info (parsing from)
            layer_obj: The backend model which holds the layer data (parsing to)
        Returns:
             nothing
        """
        crs = xml_helper.try_get_element_from_xml("./{}CRS".format(self.get_parser_prefix()), layer)
        for elem in crs:
            layer_obj.capability_projection_system.append(elem.text)

    def parse_dimension(self, layer, layer_obj):
        """ The version specific implementation of the dimension parsing

        Args:
            layer: The xml element which holds the layer info (parsing from)
            layer_obj: The backend model which holds the layer data (parsing to)
        Returns:
             nothing
        """
        dims_list = []
        try:
            dims = xml_helper.try_get_element_from_xml(elem="./{}Dimension".format(self.get_parser_prefix()), xml_elem=layer)
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
        """ The version specific implementation of service metadata parsing

        There are elements in the <Service> part fo the GetCapabilities document which are not covered in the regular
        service metadata parsing due to the fact, they are only used in the newest version of WMS which is by far not
        regularly used.

        Args:
            xml_obj: The xml element
        Returns:
             nothing
        """
        # layer limit is new
        layer_limit = xml_helper.try_get_text_from_xml_element(elem="//{}LayerLimit".format(self.get_parser_prefix()), xml_elem=xml_obj)
        self.layer_limit = layer_limit
        # max height and width is new
        max_width = xml_helper.try_get_text_from_xml_element(elem="//{}MaxWidth".format(self.get_parser_prefix()), xml_elem=xml_obj)
        self.max_width = max_width
        max_height = xml_helper.try_get_text_from_xml_element(elem="//{}MaxHeight".format(self.get_parser_prefix()), xml_elem=xml_obj)
        self.max_height = max_height
        self.get_layers(xml_obj=xml_obj)