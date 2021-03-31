"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 29.04.19

"""
import json

import requests

from MrMap.cacher import EPSGCacher
from MrMap.settings import PROXIES, XML_NAMESPACES
from service.helper import xml_helper
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum


class EpsgApi:
    def __init__(self):
        self.registry_uri = "http://www.epsg-registry.org/export.htm?gml="
        self.id_prefix = "urn:ogc:def:crs:EPSG::"

        # Cacher
        self.cacher = EPSGCacher()

    def get_subelements(self, identifier: str):
        """ Returns both, id and prefix in a dict

        Args:
            identifier: The unresolved identifier for an SRS
        Returns:
             A dict containing the parts of the identifier
        """
        id = self.get_real_identifier(identifier)
        prefix = identifier[:len(identifier) - len(str(id))]
        return {
            "code": id,
            "prefix": prefix,
        }

    def get_real_identifier(self, identifier: str):
        """ Returns only the numeral identifier of the spatial reference system.

        E.g. for 'EPSG:1111' the integer 1111 will be returned

        Args:
            identifier (str): The unresolved identifier for an SRS
        Returns:
             identifier_num (int): The integer identifier
        """

        id_list = identifier.split(":")
        identifier_num = -1
        for part in id_list:
            try:
                identifier_num = int(part)
            except ValueError:
                pass
        return identifier_num

    def _get_axis_order(self, identifier: str):
        """ Returns the axis order for a given spatial result system

        Args:
            identifier:
        Returns:

        """
        id = self.get_real_identifier(identifier)

        axis_order = self.cacher.get(str(id))
        if axis_order is not None:
            axis_order = json.loads(axis_order)
            return axis_order

        XML_NAMESPACES["gml"] = "http://www.opengis.net/gml/3.2"

        uri = self.registry_uri + self.id_prefix + str(id)
        response = requests.request("Get", url=uri, proxies=PROXIES)
        response = xml_helper.parse_xml(str(response.content.decode()))
        type = xml_helper.try_get_text_from_xml_element(xml_elem=response, elem="//epsg:type")
        if type == "projected":
            cartes_elem = xml_helper.try_get_single_element_from_xml("//gml:cartesianCS", response)
            second_level_srs_uri = xml_helper.get_href_attribute(xml_elem=cartes_elem)
        elif type == "geographic 2D":
            geogr_elem = xml_helper.try_get_single_element_from_xml("//gml:ellipsoidalCS", response)
            second_level_srs_uri = xml_helper.get_href_attribute(xml_elem=geogr_elem)
        else:
            second_level_srs_uri = ""

        uri = self.registry_uri + second_level_srs_uri
        response = requests.request("Get", url=uri, proxies=PROXIES)
        response = xml_helper.parse_xml(str(response.content.decode()))
        axis = xml_helper.try_get_element_from_xml("//gml:axisDirection", response)
        order = []
        for a in axis:
            order.append(a.text)
        order = {
            "first_axis": order[0],
            "second_axis": order[1],
        }

        # Write this to cache, so it can be used on another request!
        self.cacher.set(str(id), json.dumps(order))

        return order

    def check_switch_axis_order(self, service_type: str, service_version: str, srs_identifier: str):
        """ Checks whether the axis have to be switched, regarding the given service type (like 'wms_1.3.0')
        and spatial reference system identifier

        Axis must be switched if order of axis for the requested srs is not (east, north)

        Args:
            service_type (str): The service type given as [type]_[version]
            srs_identifier (str): The spatial reference system, e.g. 'EPSG:4326'
        Returns:
             ret_val (bool): Whether the axis have to be switched or not
        """
        service_type = service_type.lower()
        service_version = service_version.lower()

        service_types_to_be_checked = {
            OGCServiceEnum.WMS.value: {
                OGCServiceVersionEnum.V_1_3_0.value: True
            },
            OGCServiceEnum.WFS.value: {
                OGCServiceVersionEnum.V_1_1_0.value: True,
                OGCServiceVersionEnum.V_2_0_0.value: True,
                OGCServiceVersionEnum.V_2_0_2.value: True,
            },
            "GML": {
                "3.2.0": True
            }
        }

        found = service_types_to_be_checked.get(service_type, {}).get(service_version, False)

        if not found:
            return False

        order = self._get_axis_order(srs_identifier)
        ret_val = (order["first_axis"] == "north" and order["second_axis"] == "east")
        return ret_val

    def perform_switch_axis_order(self, vertices: list):
        """ Switches axis for given list of vertices of a geometry

        Args:
            vertices (list): The list of vertices
        Returns:
             vertices (list): The list of vertices with switched axis
        """

        for i in range(0, len(vertices) - 1, 2):
            tmp = vertices[i]
            vertices[i] = vertices[i + 1]
            vertices[i + 1] = tmp
        return vertices