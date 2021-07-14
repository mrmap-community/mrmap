from eulxml import xmlmap
from resourceNew.parsers.consts import NS_WC
from resourceNew.parsers.iso.iso_metadata import IsoMetadata


class GetRecordsResponse(xmlmap.XmlObject):
    total_records = xmlmap.IntegerField(xpath=f"//{NS_WC}SearchResults']/@numberOfRecordsMatched")
    returned_records = xmlmap.IntegerField(xpath=f"//{NS_WC}SearchResults']/@numberOfRecordsReturned")
    next_record = xmlmap.IntegerField(xpath=f"//{NS_WC}SearchResults']/@nextRecord")

    records = xmlmap.NodeListField(xpath=f"//{NS_WC}SearchResults']/{NS_WC}MD_Metadata']",
                                   node_class=IsoMetadata)

