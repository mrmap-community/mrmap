from eulxml import xmlmap
from resourceNew.parsers.mixins import DBModelConverterMixin


class DatasetMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.DatasetMetadata'

    file_identifier = xmlmap.StringField(xpath="//gmd:MD_Metadata/gmd:fileIdentifier/gco:CharacterString")
    character_set_code = xmlmap.StringField(xpath="//gmd:MD_Metadata/gmd:characterSet/gmd:MD_CharacterSetCode/@codeListValue")
    date_stamp = xmlmap.DateTimeField(xpath="//gmd:MD_Metadata/gmd:dateStamp/gco:Date")
    # last_change_date = xmlmap.StringField(xpath="//gmd:MD_Metadata/gmd:dateStamp/gco:Date")
    # md_standard_name = xmlmap.StringField(xpath="//gmd:metadataStandardName/gco:CharacterString")
    # md_standard_version = xmlmap.StringField(xpath="//gmd:metadataStandardVersion/gco:CharacterString")


class IsoMetadata(xmlmap.XmlObject):
    pass
