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

from service.helper.ogc.capabilities.Service import Service
from service.models import Metadata


class WMS130Builder():
    def __init__(self, metadata: Metadata):
        self.xml_doc_obj = None
        self.metadata = metadata

    def generate_xml(self):
        contact_information = {
            "contact_person": self.metadata.contact.person_name,
            "contact_organization": self.metadata.contact.organization_name,
            "contact_position": self.metadata.contact.pos,
            "address_type": self.metadata.contact.address_type,
            "address": self.metadata.contact.address,
            "city": self.metadata.contact.city,
            "state_or_province": self.metadata.contact.state_or_province,
            "post_code": self.metadata.contact.postal_code,
            "country": self.metadata.contact.country,
            "contact_voice_telephone": self.metadata.contact.phone,
            "contact_electronic_mail_address": self.metadata.contact.email,
        }
        service_xml = Service(
            self.metadata.identifier,
            self.metadata.title,
            self.metadata.abstract,
            list(self.metadata.keywords_list.all()),
            self.metadata.online_resource,
            contact_information,
            self.metadata.fees,
            self.metadata.access_constraints,
            layer_limit=None,
            max_width=None,
            max_height=None
        )
        print(service_xml)

    def build_xml(self):
        """ Generate an xml capabilities document from the metadata object

        Args:
            metadata (Metadata): Metadata of the requested service
        Returns:
             nothing
        """
        root = et.Element('WMS_Capabilities')
        service = et.SubElement(root, "Service")
        capability = et.SubElement(root, "Capability")
        self._build_service_xml(service, self.metadata)
        self.xml_doc = root

    def _build_service_xml(self, service):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service: The service xml object
            metadata (Metadata): The metadata of the requested service
        Returns:
            nothing
        """
        et.SubElement(service, "Name")
        et.SubElement(service, "Title")
        xml_keyword_list = et.SubElement(service, "KeywordList")
        for kw in self.metadata.keywords.all():
            xml_kw = et.SubElement(xml_keyword_list, "Keyword")
            xml_kw.text = kw.keyword