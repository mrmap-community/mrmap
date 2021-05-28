from django.contrib.gis.geos import Polygon as GeosPolygon
from django.contrib.gis.geos import MultiPolygon
from eulxml import xmlmap

from resourceNew.parsers.consts import NS_WC
from resourceNew.parsers.mixins import DBModelConverterMixin
from pathlib import Path
import urllib

from service.helper.epsg_api import EpsgApi


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.Keyword"

    keyword = xmlmap.StringField(xpath=".")


class Category(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.Category"

    category = xmlmap.StringField(xpath=".")


class Dimension(DBModelConverterMixin, xmlmap.XmlObject):
    # todo:
    temporal_extent_start = xmlmap.DateTimeField(xpath="gmd:extent/gml:TimePeriod/gml:beginPosition")
    temporal_extent_start_indeterminate_position = xmlmap.StringField(xpath="gmd:extent/gml:TimePeriod/gml:beginPosition/@indeterminatePosition")
    temporal_extent_end = xmlmap.DateTimeField(xpath="gmd:extent/gml:TimePeriod/gml:endPosition")
    temporal_extent_end_indeterminate_position = xmlmap.StringField(xpath="gmd:extent/gml:TimePeriod/gml:endPosition/@indeterminatePosition")


class EXGeographicBoundingBox(xmlmap.XmlObject):
    min_x = xmlmap.FloatField(xpath="gmd:westBoundLongitude/gco:Decimal")
    max_x = xmlmap.FloatField(xpath="gmd:eastBoundLongitude/gco:Decimal")
    min_y = xmlmap.FloatField(xpath="gmd:southBoundLatitude/gco:Decimal")
    max_y = xmlmap.FloatField(xpath="gmd:northBoundLatitude/gco:Decimal")

    def to_polygon(self):
        if self.min_x and self.max_x and self.min_y and self.max_y:
            return GeosPolygon(((self.min_x, self.min_y),
                               (self.min_x, self.max_y),
                               (self.max_x, self.max_y),
                               (self.max_x, self.min_y),
                               (self.min_x, self.min_y)))


class LinearRing(xmlmap.XmlObject):
    pos_list = xmlmap.StringField(xpath="gml:LinearRing/gml:posList")
    coordinates = xmlmap.StringField(xpath="gml:LinearRing/gml:coordinates")

    def to_polygon(self):
        if self.pos_list:
            cords = self.pos_list.split(" ")
            return GeosPolygon(((cords[i], cords[i + 2]) for i in range(0, len(cords), 2)))
        elif self.coordinates:
            # todo: find test data and implement it
            pass


class Polygon(xmlmap.XmlObject):
    srs = xmlmap.StringField(xpath="@srsName")
    exterior = xmlmap.NodeField(xpath="gml:exterior", node_class=LinearRing)
    interior_list = xmlmap.NodeListField(xpath="gml:interior", node_class=LinearRing)

    def to_polygon(self):
        if self.exterior:
            return self.exterior.to_polygon()
        elif self.interior_list:
            polygon_list = []
            for interior in self.interior_list:
                polygon_list.append(interior.to_polygon())
            return MultiPolygon(polygon_list)


class EXBoundingPolygon(xmlmap.XmlObject):
    polygon_list = xmlmap.NodeListField(xpath="//gmd:polygon/gml:Polygon", node_class=Polygon)

    def to_polygon(self):
        if self.polygon_list:
            return self.polygon_list.to_polygon()


class ReferenceSystem(DBModelConverterMixin, xmlmap.XmlObject):
    ref_system = xmlmap.StringField(xpath="gmd:code/gco:CharacterString")
    ref_system_version = xmlmap.StringField(xpath="gmd:version/gco:CharacterString")
    ref_system_authority = xmlmap.StringField(xpath="gmd:authority/gmd:CI_Citation/gmd:title/gco:CharacterString")

    def get_field_dict(self):
        field_dict = super().get_field_dict()

        epsg_api = EpsgApi()
        if self.ref_system is not None:
            self.ref_system = "EPSG:{}".format(epsg_api.get_subelements(self.ref_system).get("code"))
        # todo
        return {}


class MetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.MetadataContact"

    name = xmlmap.StringField(xpath='gmd:organisationName/gco:CharacterString')
    person_name = xmlmap.StringField(xpath='gmd:individualName/gco:CharacterString')
    phone = xmlmap.StringField(xpath='gmd:contactInfo/gmd:CI_Contact/gmd:phone/gmd:CI_Telephone/gmd:voice/gco:CharacterString')
    email = xmlmap.StringField(xpath='gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString')


class IsoMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.ServiceMetadata"

    title = xmlmap.StringField(xpath="gmd:identificationInfo//gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString")
    abstract = xmlmap.StringField(xpath="gmd:identificationInfo//gmd:abstract/gco:CharacterString")
    # language = xmlmap.StringField(xpath="gmd:identificationInfo//gmd:language/gmd:LanguageCode")
    access_constraints = xmlmap.StringField(xpath='gmd:identificationInfo//gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue="otherRestrictions"]/gmd:otherConstraints/gco:CharacterString')

    file_identifier = xmlmap.StringField(xpath="gmd:fileIdentifier/gco:CharacterString")
    # character_set_code = xmlmap.StringField(xpath="gmd:characterSet/gmd:MD_CharacterSetCode/@codeListValue")
    date_stamp_date = xmlmap.DateField(xpath="gmd:dateStamp/gco:Date")
    date_stamp_date_time = xmlmap.DateTimeField(xpath="gmd:dateStamp/gco:DateTime")
    hierarchy_level = xmlmap.StringField(xpath="gmd:hierarchyLevel/gmd:MD_ScopeCode/@codeListValue")

    equivalent_scale = xmlmap.FloatField(xpath="gmd:identificationInfo//gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer")
    ground_res = xmlmap.FloatField(xpath="gmd:identificationInfo//gmd:spatialResolution/gmd:MD_Resolution/gmd:distance/gco:Distance")

    bbox_lat_lon_list = xmlmap.NodeListField(xpath="//gmd:identificationInfo//gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_GeographicBoundingBox", node_class=EXGeographicBoundingBox)
    bounding_polygon_list = xmlmap.NodeListField(xpath="//gmd:identificationInfo//gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon", node_class=EXBoundingPolygon)

    metadata_contact = xmlmap.NodeField(xpath="gmd:contact/gmd:CI_ResponsibleParty", node_class=MetadataContact)
    dataset_contact = xmlmap.NodeField(xpath="gmd:identificationInfo/gmd:MD_DataIdentification/gmd:pointOfContact/gmd:CI_ResponsibleParty", node_class=MetadataContact)

    keywords = xmlmap.NodeListField(xpath="gmd:identificationInfo//gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword/gco:CharacterString", node_class=Keyword)
    categories = xmlmap.NodeListField(xpath="gmd:identificationInfo//gmd:topicCategory/gmd:MD_TopicCategoryCode", node_class=Category)

    # todo:
    reference_systems = xmlmap.NodeListField(xpath="gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier", node_class=ReferenceSystem)

    # todo:
    dimensions = xmlmap.NodeListField(xpath="gmd:identificationInfo/gmd:MD_DataIdentification/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent", node_class=Dimension)

    # dataset specific fields
    code_md = xmlmap.StringField(xpath="gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString")
    code_rs = xmlmap.StringField(xpath="gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:RS_Identifier/gmd:code/gco:CharacterString")
    code_space_rs = xmlmap.StringField("gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:RS_Identifier/gmd:codeSpace/gco:CharacterString")

    def get_model_class(self):
        if self.hierarchy_level == "service":
            self.model = "resourceNew.ServiceMetadata"
        else:
            self.model = "resourceNew.DatasetMetadata"
        return super().get_model_class()

    def get_bounding_geometry(self):
        polygon_list = []
        for bbox in self.bbox_lat_lon_list:
            polygon_list.append(bbox.to_polygon())
        for polygon in self.bounding_polygon_list:
            _polygon = polygon.to_polygon()
            if _polygon:
                polygon_list.append(_polygon)
        return MultiPolygon(polygon_list)

    def get_spatial_res(self, field_dict):
        if self.equivalent_scale is not None and self.equivalent_scale > 0:
            field_dict["spatial_res_value"] = self.equivalent_scale
            field_dict["spatial_res_type"] = "scaleDenominator"
        elif self.ground_res is not None and self.ground_res > 0:
            field_dict["spatial_res_value"] = self.ground_res
            field_dict["spatial_res_type"] = "groundDistance"
        del field_dict["equivalent_scale"], field_dict["ground_res"]

    def get_dataset_id(self, field_dict):
        if field_dict["code_md"]:
            code = field_dict["code_md"]
            # new implementation:
            # http://inspire.ec.europa.eu/file/1705/download?token=iSTwpRWd&usg=AOvVaw18y1aTdkoMCBxpIz7tOOgu
            # from 2017-03-02 - the MD_Identifier - see C.2.5 Unique resource identifier - it is separated with a slash
            # - the codes pace should be everything after the last slash
            # now try to check if a single slash is available and if the md_identifier is a url
            parsed_url = urllib.parse.urlsplit(code)
            if parsed_url.scheme == "http" or parsed_url.scheme == "https" and "/" in parsed_url.path:
                tmp = code.split("/")
                field_dict["dataset_id"] = tmp[len(tmp) - 1]
                field_dict["dataset_id_code_space"] = code.replace(field_dict["dataset_id"], "")
            elif parsed_url.scheme == "http" or parsed_url.scheme == "https" and "#" in code:
                tmp = code.split("#")
                field_dict["dataset_id"] = tmp[1]
                field_dict["dataset_id_code_space"] = tmp[0]
            else:
                field_dict["dataset_id"] = code
                field_dict["dataset_id_code_space"] = ""
            del field_dict["code_md"]
        else:
            # try to read code from RS_Identifier
            code = field_dict["code_rs"]
            code_space = field_dict["code_space_rs"]
            if code_space is not None and code is not None and len(code_space) > 0 and len(code) > 0:
                field_dict["dataset_id"] = code
                field_dict["dataset_id_code_space"] = code_space
            else:
                field_dict["is_broken"] = True
            del field_dict["code_rs"], field_dict["code_space_rs"]

    def get_date_stamp(self, field_dict):
        date = field_dict.get("date_stamp_date", None)
        date_time = field_dict.get("date_stamp_date_time", None)
        if date:
            field_dict.update({"date_stamp": date})
            del field_dict["date_stamp_date"]
        elif date_time:
            field_dict.update({"date_stamp": date_time})
            del field_dict["date_stamp_date_time"]

    def get_field_dict(self):
        field_dict = super().get_field_dict()

        field_dict["bounding_geometry"] = self.get_bounding_geometry()

        self.get_spatial_res(field_dict=field_dict)
        self.get_dataset_id(field_dict=field_dict)
        self.get_date_stamp(field_dict=field_dict)

        del field_dict["hierarchy_level"]

        return field_dict


class WrappedIsoMetadata(xmlmap.XmlObject):
    iso_metadata = xmlmap.NodeField(xpath=f"//{NS_WC}MD_Metadata']", node_class=IsoMetadata)
