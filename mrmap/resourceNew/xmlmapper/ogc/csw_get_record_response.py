from eulxml import xmlmap
from resourceNew.xmlmapper.consts import NS_WC
from resourceNew.xmlmapper.iso_metadata.iso_metadata import MdMetadata


class GetRecordsResponse(xmlmap.XmlObject):
    total_records = xmlmap.IntegerField(xpath=f"//{NS_WC}SearchResults']/@numberOfRecordsMatched")
    returned_records = xmlmap.IntegerField(xpath=f"//{NS_WC}SearchResults']/@numberOfRecordsReturned")
    next_record = xmlmap.IntegerField(xpath=f"//{NS_WC}SearchResults']/@nextRecord")

    records = xmlmap.NodeListField(xpath=f"//{NS_WC}SearchResults']//{NS_WC}MD_Metadata']",
                                   node_class=MdMetadata)

