from django.contrib.gis.geos import Polygon as GeosPolygon
from django.contrib.gis.geos import MultiPolygon
from eulxml import xmlmap
from resourceNew.parsers.consts import NS_WC
from resourceNew.parsers.mixins import DBModelConverterMixin
import urllib


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.Keyword"

    keyword = xmlmap.StringField(xpath=".")


class Category(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.Category"

    category = xmlmap.StringField(xpath=".")


class Dimension(DBModelConverterMixin, xmlmap.XmlObject):
    # todo:
    temporal_extent_start = xmlmap.DateTimeField(xpath=f"{NS_WC}extent']/{NS_WC}TimePeriod']/{NS_WC}beginPosition']")
    temporal_extent_start_indeterminate_position = xmlmap.StringField(xpath=f"{NS_WC}extent']/{NS_WC}TimePeriod']/{NS_WC}beginPosition']/@indeterminatePosition")
    temporal_extent_end = xmlmap.DateTimeField(xpath=f"{NS_WC}extent']/{NS_WC}TimePeriod']/{NS_WC}endPosition']")
    temporal_extent_end_indeterminate_position = xmlmap.StringField(xpath=f"{NS_WC}extent']/{NS_WC}TimePeriod']/{NS_WC}endPosition']/@indeterminatePosition")


class EXGeographicBoundingBox(xmlmap.XmlObject):
    min_x = xmlmap.FloatField(xpath=f"{NS_WC}westBoundLongitude']/{NS_WC}Decimal']")
    max_x = xmlmap.FloatField(xpath=f"{NS_WC}eastBoundLongitude']/{NS_WC}Decimal']")
    min_y = xmlmap.FloatField(xpath=f"{NS_WC}southBoundLatitude']/{NS_WC}Decimal']")
    max_y = xmlmap.FloatField(xpath=f"{NS_WC}northBoundLatitude']/{NS_WC}Decimal']")

    def to_polygon(self):
        if self.min_x and self.max_x and self.min_y and self.max_y:
            return GeosPolygon(((self.min_x, self.min_y),
                               (self.min_x, self.max_y),
                               (self.max_x, self.max_y),
                               (self.max_x, self.min_y),
                               (self.min_x, self.min_y)))


class LinearRing(xmlmap.XmlObject):
    pos_list = xmlmap.StringField(xpath=f"{NS_WC}LinearRing']/{NS_WC}posList']")
    coordinates = xmlmap.StringField(xpath=f"{NS_WC}LinearRing']/{NS_WC}coordinates']")

    def to_polygon(self):
        if self.pos_list:
            cords = self.pos_list.split(" ")
            return GeosPolygon(((cords[i], cords[i + 2]) for i in range(0, len(cords), 2)))
        elif self.coordinates:
            # todo: find test data and implement it
            pass


class Polygon(xmlmap.XmlObject):
    srs = xmlmap.StringField(xpath="@srsName")
    exterior = xmlmap.NodeField(xpath=f"{NS_WC}exterior']", node_class=LinearRing)
    interior_list = xmlmap.NodeListField(xpath=f"{NS_WC}interior']", node_class=LinearRing)

    def to_polygon(self):
        if self.exterior:
            return self.exterior.to_polygon()
        elif self.interior_list:
            polygon_list = []
            for interior in self.interior_list:
                polygon_list.append(interior.to_polygon())
            return MultiPolygon(polygon_list)


class EXBoundingPolygon(xmlmap.XmlObject):
    polygon_list = xmlmap.NodeListField(xpath=f"//{NS_WC}polygon']/{NS_WC}Polygon']", node_class=Polygon)

    def to_polygon(self):
        if self.polygon_list:
            return self.polygon_list.to_polygon()


class ReferenceSystem(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.ReferenceSystem"

    ref_system = xmlmap.StringField(xpath=f"{NS_WC}code']/{NS_WC}CharacterString']")

    def get_field_dict(self):
        field_dict = super().get_field_dict()
        if field_dict.get("ref_system", None):
            if "http://www.opengis.net/def/crs/" in field_dict["ref_system"]:
                code = field_dict["ref_system"].split("/")[-1]
            else:
                code = field_dict["ref_system"].split(":")[-1]
            field_dict.update({"code": code})

        del field_dict["ref_system"]

        return field_dict


class MetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.MetadataContact"

    name = xmlmap.StringField(xpath=f"{NS_WC}organisationName']/{NS_WC}CharacterString']")
    person_name = xmlmap.StringField(xpath=f"{NS_WC}individualName']/{NS_WC}CharacterString']")
    phone = xmlmap.StringField(xpath=f"{NS_WC}contactInfo']/{NS_WC}CI_Contact']/{NS_WC}phone']/{NS_WC}CI_Telephone']/{NS_WC}voice']/{NS_WC}CharacterString']")
    email = xmlmap.StringField(xpath=f"{NS_WC}contactInfo']/{NS_WC}CI_Contact']/{NS_WC}address']/{NS_WC}CI_Address']/{NS_WC}electronicMailAddress']/{NS_WC}CharacterString']")


class IsoMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.ServiceMetadata"

    title = xmlmap.StringField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}citation']/{NS_WC}CI_Citation']/{NS_WC}title']/{NS_WC}CharacterString']")
    abstract = xmlmap.StringField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}abstract']/{NS_WC}CharacterString']")
    # language = xmlmap.StringField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}language']/{NS_WC}LanguageCode']")
    access_constraints = xmlmap.StringField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}resourceConstraints']/{NS_WC}MD_LegalConstraints'][{NS_WC}accessConstraints']/{NS_WC}MD_RestrictionCode']/@codeListValue=\"otherRestrictions\"]/{NS_WC}otherConstraints']/{NS_WC}CharacterString']")

    file_identifier = xmlmap.StringField(xpath=f"{NS_WC}fileIdentifier']/{NS_WC}CharacterString']")
    # character_set_code = xmlmap.StringField(xpath=f"{NS_WC}characterSet']/{NS_WC}MD_CharacterSetCode']/@codeListValue")
    date_stamp_date = xmlmap.DateField(xpath=f"{NS_WC}dateStamp']/{NS_WC}Date']")
    date_stamp_date_time = xmlmap.DateTimeField(xpath=f"{NS_WC}dateStamp']/{NS_WC}DateTime']")
    hierarchy_level = xmlmap.StringField(xpath=f"{NS_WC}hierarchyLevel']/{NS_WC}MD_ScopeCode']/@codeListValue")

    equivalent_scale = xmlmap.FloatField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}spatialResolution']/{NS_WC}MD_Resolution']/{NS_WC}equivalentScale']/{NS_WC}MD_RepresentativeFraction']/{NS_WC}denominator']/{NS_WC}Integer']")
    ground_res = xmlmap.FloatField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}spatialResolution']/{NS_WC}MD_Resolution']/{NS_WC}distance']/{NS_WC}Distance']")

    bbox_lat_lon_list = xmlmap.NodeListField(xpath=f"//{NS_WC}identificationInfo']//{NS_WC}extent']/{NS_WC}EX_Extent']/{NS_WC}geographicElement']/{NS_WC}EX_GeographicBoundingBox']", node_class=EXGeographicBoundingBox)
    bounding_polygon_list = xmlmap.NodeListField(xpath=f"//{NS_WC}identificationInfo']//{NS_WC}extent']/{NS_WC}EX_Extent']/{NS_WC}geographicElement']/{NS_WC}EX_BoundingPolygon']", node_class=EXBoundingPolygon)

    metadata_contact = xmlmap.NodeField(xpath=f"{NS_WC}contact']/{NS_WC}CI_ResponsibleParty']", node_class=MetadataContact)
    dataset_contact = xmlmap.NodeField(xpath=f"{NS_WC}identificationInfo']/{NS_WC}MD_DataIdentification']/{NS_WC}pointOfContact']/{NS_WC}CI_ResponsibleParty']", node_class=MetadataContact)

    keywords = xmlmap.NodeListField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}descriptiveKeywords']/{NS_WC}MD_Keywords']/{NS_WC}keyword']/{NS_WC}CharacterString']", node_class=Keyword)
    categories = xmlmap.NodeListField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}topicCategory']/{NS_WC}MD_TopicCategoryCode']", node_class=Category)

    reference_systems = xmlmap.NodeListField(xpath=f"{NS_WC}referenceSystemInfo']/{NS_WC}MD_ReferenceSystem']/{NS_WC}referenceSystemIdentifier']/{NS_WC}RS_Identifier']", node_class=ReferenceSystem)

    # todo:
    dimensions = xmlmap.NodeListField(xpath=f"{NS_WC}identificationInfo']/{NS_WC}MD_DataIdentification']/{NS_WC}extent']/{NS_WC}EX_Extent']/{NS_WC}temporalElement']/{NS_WC}EX_TemporalExtent']", node_class=Dimension)

    # dataset specific fields
    code_md = xmlmap.StringField(xpath=f"{NS_WC}identificationInfo']/{NS_WC}MD_DataIdentification']/{NS_WC}citation']/{NS_WC}CI_Citation']/{NS_WC}identifier']/{NS_WC}MD_Identifier']/{NS_WC}code']/{NS_WC}CharacterString']")
    code_rs = xmlmap.StringField(xpath=f"{NS_WC}identificationInfo']/{NS_WC}MD_DataIdentification']/{NS_WC}citation']/{NS_WC}CI_Citation']/{NS_WC}identifier']/{NS_WC}RS_Identifier']/{NS_WC}code']/{NS_WC}CharacterString']")
    code_space_rs = xmlmap.StringField(f"{NS_WC}identificationInfo']/{NS_WC}MD_DataIdentification']/{NS_WC}citation']/{NS_WC}CI_Citation']/{NS_WC}identifier']/{NS_WC}RS_Identifier']/{NS_WC}codeSpace']/{NS_WC}CharacterString']")

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
        if field_dict.get("code_md", None):
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

        elif field_dict.get("code_rs", None):
            # try to read code from RS_Identifier
            code = field_dict["code_rs"]
            code_space = field_dict["code_space_rs"]
            if code_space is not None and code is not None and len(code_space) > 0 and len(code) > 0:
                field_dict["dataset_id"] = code
                field_dict["dataset_id_code_space"] = code_space
            else:
                field_dict["is_broken"] = True

        del field_dict["code_rs"], field_dict["code_space_rs"], field_dict["code_md"]

    def get_date_stamp(self, field_dict):
        date = field_dict.get("date_stamp_date", None)
        date_time = field_dict.get("date_stamp_date_time", None)
        if date:
            field_dict.update({"date_stamp": date})
        elif date_time:
            field_dict.update({"date_stamp": date_time})
        del field_dict["date_stamp_date"], field_dict["date_stamp_date_time"]

    def get_field_dict(self):
        field_dict = super().get_field_dict()

        field_dict["bounding_geometry"] = self.get_bounding_geometry()

        self.get_spatial_res(field_dict=field_dict)
        self.get_dataset_id(field_dict=field_dict)
        self.get_date_stamp(field_dict=field_dict)

        del field_dict["hierarchy_level"]

        return field_dict


class WrappedIsoMetadata(xmlmap.XmlObject):
    # /*[namespace-uri()='http://www.isotc211.org/2005/gmd' and local-name()='MD_Metadata']
    iso_metadata = xmlmap.NodeField(xpath=f"//{NS_WC}MD_Metadata']", node_class=IsoMetadata)


