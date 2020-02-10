"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 31.07.19


    ATTENTION!!!
    THIS IS CURRENTLY NOT UNDER DEVELOPMENT!
    HOWEVER, SINCE WE WILL NEED CREATION OF XML IN THE FUTURE FOR OTHER FEATURES, THIS WILL BE KEPT IN THE CURRENT STATE
    AS A REFERENCE OF HOW THINGS COULD BE DONE. FOR FURTHER INFORMATION READ
    https://github.com/josuebrunel/pysxm

"""
import xml.etree.ElementTree as et

from lxml.etree import _Element

from MapSkinner.settings import XML_NAMESPACES
from service.helper import xml_helper
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum
from service.helper.ogc.capabilities.Service import Service
from service.models import Metadata

class CapabilityXMLBuilder:
    def __init__(self, service: Service):
        self.service = service
        self.metadata = service.metadata

        self.service_type = service.servicetype.name
        self.service_version = service.servicetype.version

    def generate_xml(self):
        xml_builder = None
        xml = ""

        if self.service_type == OGCServiceEnum.WMS.value:

            if self.service_version == OGCServiceVersionEnum.V_1_0_0.value:
                xml_builder = CapabilityWMS100Builder(self.service)

            elif self.service_version == OGCServiceVersionEnum.V_1_1_1.value:
                xml_builder = CapabilityWMS111Builder(self.service)

            elif self.service_version == OGCServiceVersionEnum.V_1_3_0.value:
                xml_builder = CapabilityWMS130Builder(self.service)

        elif self.service_type == OGCServiceEnum.WFS.value:

            if self.service_version == OGCServiceVersionEnum.V_1_0_0.value:
                xml_builder = CapabilityWFS100Builder(self.service)

            elif self.service_version == OGCServiceVersionEnum.V_1_1_0.value:
                xml_builder = CapabilityWFS110Builder(self.service)

            elif self.service_version == OGCServiceVersionEnum.V_2_0_0.value:
                xml_builder = CapabilityWFS200Builder(self.service)

            elif self.service_version == OGCServiceVersionEnum.V_2_0_2.value:
                xml_builder = CapabilityWFS202Builder(self.service)

        xml = xml_builder.generate_xml()
        return xml

class CapabilityWMS100Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

class CapabilityWMS111Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

class CapabilityWMS130Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        self.namespaces = {
            "sld": XML_NAMESPACES["sld"],
            "xsi": XML_NAMESPACES["xsi"],
            "default": XML_NAMESPACES["wms"],
        }
        self.ns_prefix = "{" + self.namespaces["default"] + "}"
        super().__init__(service=service)

    def generate_xml(self):
        """ Generate an xml capabilities document from the metadata object

        Args:
            metadata (Metadata): Metadata of the requested service
        Returns:
             nothing
        """
        root = et.Element(
            'WMS_Capabilities',
            attrib={
                "version": self.service_version
            }
        )
        self.xml_doc_obj = root

        service = et.SubElement(root, "{}Service".format(self.ns_prefix))
        self._generate_service_xml(service)
        xml_helper.add_subelement(root, service)

        capability = et.SubElement(root, "{}Capability".format(self.ns_prefix))
        self._generate_capability_xml(service)
        xml_helper.add_subelement(root, capability)

        return xml_helper.xml_to_string(root)


    def _generate_service_xml(self, service_elem: _Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        md:Metadata

        name_elem = xml_helper.create_subelement(service_elem, "Name")
        xml_helper.write_text_to_element(name_elem, txt=md.identifier)

        name_elem = xml_helper.create_subelement(service_elem, "Title")
        xml_helper.write_text_to_element(name_elem, txt=md.title)

        name_elem = xml_helper.create_subelement(service_elem, "Abstract")
        xml_helper.write_text_to_element(name_elem, txt=md.abstract)


        xml_keyword_list = et.SubElement(service_elem, "KeywordList")
        for kw in self.metadata.keywords.all():
            xml_kw = et.SubElement(xml_keyword_list, "{}Keyword".format(self.ns_prefix))
            xml_kw.text = kw.keyword

    def _generate_capability_xml(self, capability_elem: _Element):
        # ToDO: Implement
        pass


class CapabilityWFS100Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

class CapabilityWFS110Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

class CapabilityWFS200Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

class CapabilityWFS202Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)