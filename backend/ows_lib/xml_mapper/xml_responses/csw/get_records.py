from eulxml.xmlmap import IntegerField, NodeListField, XmlObject
from ows_lib.xml_mapper.iso_metadata.iso_metadata import MdMetadata
from ows_lib.xml_mapper.namespaces import CSW_2_0_2_NAMESPACE, GMD_NAMESPACE


class CswRecord(XmlObject):
    ROOT_NAME = "Record"
    ROOT_NS = CSW_2_0_2_NAMESPACE
    ROOT_NAMESPACES = {
        "csw": CSW_2_0_2_NAMESPACE,
    }


class GetRecordsResponse(XmlObject):
    ROOT_NAME = "GetRecordsResponse"
    ROOT_NS = CSW_2_0_2_NAMESPACE
    ROOT_NAMESPACES = {
        "csw": CSW_2_0_2_NAMESPACE,
        "gmd": GMD_NAMESPACE
    }

    XSD_SCHEMA = "http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"

    next_record = IntegerField(xpath="./csw:SearchResults/@nextRecord")
    total_records = IntegerField(
        xpath="./csw:SearchResults/@numberOfRecordsMatched")
    records_returned = IntegerField(
        xpath="./csw:SearchResults/@numberOfRecordsReturned")

    csw_records = NodeListField(
        xpath="./csw:SearchResults/csw:Record", node_class=CswRecord)
    gmd_records = NodeListField(
        xpath="./csw:SearchResults/gmd:MD_Metadata", node_class=MdMetadata)
