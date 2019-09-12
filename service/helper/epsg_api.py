"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 29.04.19

"""
import requests

from MapSkinner.settings import PROXIES, XML_NAMESPACES
from service.helper import service_helper, xml_helper


class EpsgApi:
    def __init__(self):
        self.registry_uri = "http://www.epsg-registry.org/export.htm?gml="
        self.id_prefix = "urn:ogc:def:crs:EPSG::"

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

    def get_axis_order(self, identifier: str):
        """ Returns the axis order for a given spatial result system

        Args:
            identifier:
        Returns:

        """
        id = self.get_real_identifier(identifier)

        XML_NAMESPACES["gml"] = "http://www.opengis.net/gml/3.2"

        uri=self.registry_uri + self.id_prefix + str(id)
        response = requests.request("Get", url=uri, proxies=PROXIES)
        response = xml_helper.parse_xml(str(response.content.decode()))
        type = xml_helper.try_get_text_from_xml_element(xml_elem=response, elem="//epsg:type")
        if type == "projected":
            second_level_srs_uri = xml_helper.try_get_attribute_from_xml_element(xml_elem=response, elem="//gml:cartesianCS", attribute="{http://www.w3.org/1999/xlink}href")
        elif type == "geographic 2D":
            second_level_srs_uri = xml_helper.try_get_attribute_from_xml_element(xml_elem=response, elem="//gml:ellipsoidalCS", attribute="{http://www.w3.org/1999/xlink}href")
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
        return order

