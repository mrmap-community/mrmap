from eulxml.xmlmap import IntegerField, NodeListField, XmlObject
from ows_lib.xml_mapper.namespaces import CSW_2_0_2_NAMESPACE


class Record(XmlObject):
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
    }

    XSD_SCHEMA = "http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"

    next_record = IntegerField(xpath="./@nextRecord")
    total_records = IntegerField(xpath="./@numberOfRecordsMatched")
    records_returned = IntegerField(xpath="./@numberOfRecordsReturned")

    records = NodeListField(
        xpath="./csw:SearchResults/csw:Record", node_class=Record)
