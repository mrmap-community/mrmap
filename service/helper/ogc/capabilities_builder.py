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
from abc import abstractmethod
from collections import OrderedDict

from lxml.etree import Element

from MapSkinner.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum
from service.helper.ogc.capabilities.Service import Service
from structure.models import Contact


class CapabilityXMLBuilder:
    def __init__(self, service: Service):
        self.service = service
        self.metadata = service.metadata

        self.service_type = service.servicetype.name
        self.service_version = service.servicetype.version

    @abstractmethod
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

    def generate_xml(self):
        xml = ""
        return xml

class CapabilityWMS111Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

    def generate_xml(self):
        xml = ""
        return xml

class CapabilityWMS130Builder(CapabilityXMLBuilder):
    """

    Creates a xml document, according to the specification of WMS 1.3.0
    http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd

    """
    def __init__(self, service: Service):
        self.xml_doc_obj = None

        self.namespaces = {
            None: XML_NAMESPACES["wms"],
            "sld": XML_NAMESPACES["sld"],
            "xlink": XML_NAMESPACES["xlink"],
            "xsi": XML_NAMESPACES["xsi"],
        }

        self.default_ns = "{" + self.namespaces.get(None) + "}"
        self.xlink_ns = "{" + XML_NAMESPACES["xlink"] + "}"

        super().__init__(service=service)

    def generate_xml(self):
        """ Generate an xml capabilities document from the metadata object

        Args:
            metadata (Metadata): Metadata of the requested service
        Returns:
             nothing
        """
        root = Element(
            '{}WMS_Capabilities'.format(self.default_ns),
            attrib={
                "version": self.service_version
            },
            nsmap=self.namespaces
        )
        self.xml_doc_obj = root

        service = xml_helper.create_subelement(root, "{}Service".format(self.default_ns))
        self._generate_service_xml(service)

        capability =  xml_helper.create_subelement(root, "{}Capability".format(self.default_ns))
        self._generate_capability_xml(service)

        return xml_helper.xml_to_string(root, pretty_print=True)


    def _generate_service_xml(self, service_elem: Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata

        contents = OrderedDict({
            "{}Name": md.identifier,
            "{}Title": md.title,
            "{}Abstract": md.abstract,
            "{}KeywordList": "",
            "{}OnlineResource": md.online_resource,
            "{}ContactInformation": "",
            "{}Fees": md.fees,
            "{}AccessConstraints": md.access_constraints,
            "{}MaxWidth": "",  # ToDo: Implement md.service.max_width in registration
            "{}MaxHeight": "",  # ToDo: Implement md.service.max_height in registration
        })

        for key, val in contents.items():
            k = key.format(self.default_ns)
            elem = xml_helper.create_subelement(service_elem, k)
            if "OnlineResource" in key:
                xml_helper.set_attribute(elem, "{}href".format(self.xlink_ns), val)
            else:
                xml_helper.write_text_to_element(elem, txt=val)

        # Add keywords to <wms:KeywordList>
        xml_keyword_list = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("KeywordList"),
            service_elem
        )
        for kw in md.keywords.all():
            xml_kw = xml_helper.create_subelement(xml_keyword_list, "{}Keyword".format(self.default_ns))
            xml_helper.write_text_to_element(xml_kw, txt=kw.keyword)

        # Fill in the data for <ContactInformation>
        contact_information_eleme = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation"),
            service_elem
        )
        self._generate_contact_information_xml(contact_information_eleme)

    def _generate_contact_information_xml(self, service_elem):
        """ Generate the 'ContactInformation' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact
        contact: Contact

        contents = OrderedDict({
            "{}ContactPersonPrimary": "",
            "{}ContactAddress": "",
            "{}ContactVoiceTelephone": contact.phone,
            "{}ContactFacsimileTelephone": contact.facsimile,
            "{}ContactElectronicMailAddress": contact.email,
        })

        for key, val in contents.items():
            k = key.format(self.default_ns)
            elem = xml_helper.create_subelement(service_elem, k)
            xml_helper.write_text_to_element(elem, txt=val)

        # Get <ContactPersonPrimary> element to fill in the data
        contact_person_primary_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactPersonPrimary"),
            service_elem
        )
        self._generate_contact_person_primary_xml(contact_person_primary_elem)

        # Get <ContactAddress> element to fill in the data
        address_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactAddress"),
            service_elem
        )
        self._generate_contact_address_xml(address_elem)

    def _generate_contact_person_primary_xml(self, contact_person_primary_elem: Element):
        """ Generate the 'ContactPersonPrimary' subelement of a xml service object

        Args:
            contact_person_primary_elem (_Element): The <ContactPersonPrimary> xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact
        contact: Contact

        contents = OrderedDict({
            "{}ContactPerson": contact.person_name,
            "{}ContactPosition": "",
        })

        for key, val in contents.items():
            k = key.format(self.default_ns)
            elem = xml_helper.create_subelement(contact_person_primary_elem, k)
            xml_helper.write_text_to_element(elem, txt=val)



    def _generate_contact_address_xml(self, address_elem: Element):
        """ Generate the 'ContactAddress' subelement of a xml service object

        Args:
            address_elem (_Element): The address xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact
        contact: Contact

        contents = {
            "{}AddressType": contact.address_type,
            "{}Address": contact.address,
            "{}City": contact.city,
            "{}StateOrProvince": contact.state_or_province,
            "{}PostCode": contact.postal_code,
            "{}Country": contact.country,
        }

        for key, val in contents.items():
            k = key.format(self.default_ns)
            address_type = xml_helper.create_subelement(address_elem, k)
            xml_helper.write_text_to_element(address_type, txt=val)


    def _generate_capability_xml(self, capability_elem: Element):
        # ToDO: Implement
        pass


class CapabilityWFS100Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

    def generate_xml(self):
        xml = ""
        return xml

class CapabilityWFS110Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

    def generate_xml(self):
        xml = ""
        return xml

class CapabilityWFS200Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

    def generate_xml(self):
        xml = ""
        return xml

class CapabilityWFS202Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service):
        self.xml_doc_obj = None
        super().__init__(service=service)

    def generate_xml(self):
        xml = ""
        return xml