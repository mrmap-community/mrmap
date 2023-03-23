import urllib

from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon as GeosPolygon
from eulxml import xmlmap
from ows_lib.xml_mapper.gml.gml import Gml
from registry.xmlmapper.mixins import DBModelConverterMixin
from registry.xmlmapper.namespaces import (GCO_NAMESPACE, GMD_NAMESPACE,
                                           GML_3_1_1_NAMESPACE, SRV_NAMESPACE)


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = "registry.Keyword"
    ROOT_NS = GMD_NAMESPACE
    ROOT_NAME = "keyword"
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE),
                            ("gco", GCO_NAMESPACE)])

    keyword = xmlmap.StringField(xpath="gco:CharacterString")


class Category(DBModelConverterMixin, xmlmap.XmlObject):
    model = "registry.Category"
    # todo:

    category = xmlmap.StringField(xpath=".")


class Dimension(DBModelConverterMixin, xmlmap.XmlObject):
    ROOT_NS = GMD_NAMESPACE
    ROOT_NAME = "extent"
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE),
                            ("gml", GML_3_1_1_NAMESPACE)])

    temporal_extent_start = xmlmap.DateTimeField(
        xpath="gml:TimePeriod/gml:beginPosition")
    temporal_extent_start_indeterminate_position = xmlmap.StringField(
        xpath="gml:TimePeriod/gml:beginPosition/@indeterminatePosition")
    temporal_extent_end = xmlmap.DateTimeField(
        xpath="gml:TimePeriod/gml:endPosition")
    temporal_extent_end_indeterminate_position = xmlmap.StringField(
        xpath="gml:TimePeriod/gml:endPosition/@indeterminatePosition")


class EXGeographicBoundingBox(xmlmap.XmlObject):
    ROOT_NS = GMD_NAMESPACE
    ROOT_NAME = "EX_GeographicBoundingBox"
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE),
                            ("gco", GCO_NAMESPACE)])

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


class EXBoundingPolygon(xmlmap.XmlObject):
    ROOT_NS = GMD_NAMESPACE
    ROOT_NAME = "EX_BoundingPolygon"
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE)])

    geometry_list = xmlmap.NodeListField(xpath="gmd:polygon",
                                         node_class=Gml)

    def get_geometries(self):
        """Return all founded gml geometries as a list of geos geometries.
        :return: a list of geos geometries
        :rtype: list
        """
        geometries = []
        for geometry in self.geometry_list:
            geometries.append(geometry.to_gml())
        return geometries


class ReferenceSystem(DBModelConverterMixin, xmlmap.XmlObject):
    model = "registry.ReferenceSystem"
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE),
                            ("gco", GCO_NAMESPACE)])

    ref_system = xmlmap.StringField(xpath="gmd:code/gco:CharacterString")

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


class CiResponsibleParty(DBModelConverterMixin, xmlmap.XmlObject):
    model = "registry.MetadataContact"
    ROOT_NAME = "CI_ResponsibleParty"
    ROOT_NS = GMD_NAMESPACE
    ROOT_NAMESPACES = dict([("gmd", "http://www.isotc211.org/2005/gmd"),
                           ("gco", "http://www.isotc211.org/2005/gco")])

    name = xmlmap.StringField(xpath="gmd:organisationName/gco:CharacterString")
    person_name = xmlmap.StringField(
        xpath="gmd:individualName/gco:CharacterString")
    phone = xmlmap.StringField(
        xpath="gmd:contactInfo/gmd:CI_Contact/gmd:phone/gmd:CI_Telephone/gmd:voice/gco:CharacterString")
    email = xmlmap.StringField(
        xpath="gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString")


class BaseIsoMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    """Base ISO Metadata class with namespace declaration common to all ISO Metadata
    XmlObjects.

    .. Note::
       This class is intended mostly for internal use, but could be
       useful when extending or adding additional ISO Metadata
       :class:`~eulxml.xmlmap.XmlObject` classes.  The
       :attr:`GMD_NAMESPACE` is mapped to the prefix **gmd**.
       :attr:`GCO_NAMESPACE` is mapped to the prefix **gco**.
    """
    ROOT_NS = GMD_NAMESPACE
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE),
                            ("gco", GCO_NAMESPACE)])


class BasicInformation(BaseIsoMetadata):
    title = xmlmap.StringField(
        xpath="gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString")
    abstract = xmlmap.StringField(xpath="gmd:abstract/gco:CharacterString")
    access_constraints = xmlmap.StringField(
        xpath="gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue=\"otherRestrictions\"]/gmd:otherConstraints/gco:CharacterString")
    # dataset specific fields
    code_md = xmlmap.StringField(
        xpath="gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString")
    code_rs = xmlmap.StringField(
        xpath="gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:RS_Identifier/gmd:code/gco:CharacterString")
    code_space_rs = xmlmap.StringField(
        xpath="gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:RS_Identifier/gmd:codeSpace/gco:CharacterString")

    # character_set_code = xmlmap.StringField(xpath=f"{NS_WC}characterSet']/{NS_WC}MD_CharacterSetCode']/@codeListValue")

    dataset_contact = xmlmap.NodeField(xpath="gmd:pointOfContact/gmd:CI_ResponsibleParty",
                                       node_class=CiResponsibleParty)
    keywords = xmlmap.NodeListField(xpath="gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword",
                                    node_class=Keyword)

    def get_bounding_geometry(self):
        polygon_list = []
        for bbox in self.bbox_lat_lon_list:  # noqa xmlmap.NodeListField provide iterator
            polygon_list.append(bbox.to_polygon())
        for polygon in self.bounding_polygon_list:  # noqa xmlmap.NodeListField provide iterator
            polygon_list.extend(polygon.get_geometries())
        return MultiPolygon(polygon_list)

    def get_spatial_res(self, field_dict):
        if self.equivalent_scale is not None and self.equivalent_scale > 0:
            field_dict["spatial_res_value"] = self.equivalent_scale
            field_dict["spatial_res_type"] = "scaleDenominator"
        elif self.ground_res is not None and self.ground_res > 0:
            field_dict["spatial_res_value"] = self.ground_res
            field_dict["spatial_res_type"] = "groundDistance"
        field_dict.pop("equivalent_scale", None)
        field_dict.pop("ground_res", None)

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
                field_dict["dataset_id_code_space"] = code.replace(
                    field_dict["dataset_id"], "")
            elif parsed_url.scheme == "http" or parsed_url.scheme == "https" and "#" in code:
                tmp = code.split("#")
                field_dict["dataset_id"] = tmp[1]
                field_dict["dataset_id_code_space"] = tmp[0]
            else:
                field_dict["dataset_id"] = code
                field_dict["dataset_id_code_space"] = ""
            del field_dict["code_md"]

        elif field_dict.get("code_rs", None):
            # try to read code from RS_Identifier
            code = field_dict["code_rs"]
            code_space = field_dict["code_space_rs"]
            if code_space is not None and code is not None and len(code_space) > 0 and len(code) > 0:
                field_dict["dataset_id"] = code
                field_dict["dataset_id_code_space"] = code_space
            else:
                field_dict["is_broken"] = True
            del field_dict["code_rs"]

        field_dict.pop("code_space_rs", None)

    def get_date_stamp(self, field_dict):
        date = field_dict.pop("date_stamp_date", None)
        date_time = field_dict.pop("date_stamp_date_time", None)
        if date:
            field_dict.update({"date_stamp": date})
        elif date_time:
            field_dict.update({"date_stamp": date_time})


class MdDataIdentification(BasicInformation):
    ROOT_NAME = "MD_DataIdentification"
    equivalent_scale = xmlmap.FloatField(
        xpath="gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer")
    ground_res = xmlmap.FloatField(
        xpath="gmd:spatialResolution/gmd:MD_Resolution/gmd:distance/gmd:Distance")
    categories = xmlmap.NodeListField(xpath="gmd:topicCategory/gmd:MD_TopicCategoryCode",
                                      node_class=Category)
    bbox_lat_lon_list = xmlmap.NodeListField(xpath="gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_GeographicBoundingBox",
                                             node_class=EXGeographicBoundingBox)
    bounding_polygon_list = xmlmap.NodeListField(xpath="gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon",
                                                 node_class=EXBoundingPolygon)
    dimensions = xmlmap.NodeListField(xpath="gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent",
                                      node_class=Dimension)


class SvOperationMetadata(BasicInformation):
    ROOT_NAME = "SV_OperationMetadata"
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE),
                            ("gco", GCO_NAMESPACE),
                            ("srv", SRV_NAMESPACE)])
    # mandatory fields
    operation = xmlmap.StringField(
        xpath="svr:operationName/gco:characterString")
    dcp = xmlmap.StringListField(
        xpath="srv:DCP/srv:DCPList[codeList='http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#DCPList']/@codeListValue")
    url = xmlmap.StringListField(
        xpath="srv:connectPoint/gmd:CI_OnlineResource/gmd:linkage/gmd:URL")


class SvServiceIdentification(BaseIsoMetadata):
    ROOT_NAME = "SV_ServiceIdentification"
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE),
                            ("gco", GCO_NAMESPACE),
                            ("srv", SRV_NAMESPACE)])
    # mandatory fields
    service_type = xmlmap.StringField(xpath="srv:serviceType/gco:LocalName")
    coupling_type = xmlmap.StringField(
        xpath="srv:couplingType/srv:SV_CouplingType[@codeList='SV_CouplingType']/@codeListValue")
    contains_operations = xmlmap.NodeListField(xpath="srv:containsOperations/svr:SV_OperationMetadata",
                                               node_class=SvOperationMetadata)
    # optional fields
    service_type_version = xmlmap.StringListField(
        xpath="srv:serviceTypeVersion/gco:characterString")
    bbox_lat_lon_list = xmlmap.NodeListField(xpath="srv:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_GeographicBoundingBox",
                                             node_class=EXGeographicBoundingBox)
    bounding_polygon_list = xmlmap.NodeListField(xpath="srv:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_BoundingPolygon",
                                                 node_class=EXBoundingPolygon)
    dimensions = xmlmap.NodeListField(xpath="srv:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent",
                                      node_class=Dimension)


class MdMetadata(BaseIsoMetadata):
    """XML mapper class to deserialize/serialize metadata information defined in the ISO 19115 specs.

    :Example:

    .. code-block:: python
       from registry.parsers.iso import iso_metadata

       # iso metadata from scratch
       iso_md = iso_metadata.IsoMetadata()
       iso_md = file_identifier = "4be3fcf9-9376-4813-9bfd-708912038635"
       iso_md.hierarchy_level = "dataset"
       ...
       iso_md.serializeDocument()  # to get the serialized xml document

       # iso metadata from other object. All field names which shall be initiated shall have the same name.
       iso_md = IsoMetadata.from_dict({"file_identifier": "4be3fcf9-9376-4813-9bfd-708912038635",
                                       "hierarchy_level": "dataset", ... })
       iso_md.serializeDocument()  # to get the serialized xml document

    """
    model = "registry.ServiceMetadata"
    ROOT_NAME = "MD_Metadata"
    ROOT_NS = GMD_NAMESPACE

    file_identifier = xmlmap.StringField(
        xpath="gmd:fileIdentifier/gco:CharacterString")
    # language = xmlmap.StringField(xpath=f"{NS_WC}identificationInfo']//{NS_WC}language']/{NS_WC}LanguageCode']")
    hierarchy_level = xmlmap.StringField(
        xpath="gmd:hierarchyLevel/gmd:MD_ScopeCode[@codeList='http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_ScopeCode']/@codeListValue")
    date_stamp_date = xmlmap.DateField(xpath="gmd:dateStamp/gco:Date")
    date_stamp_date_time = xmlmap.DateTimeField(
        xpath="gmd:dateStamp/gco:DateTime")
    metadata_contact = xmlmap.NodeField(
        xpath="gmd:contact/gmd:CI_ResponsibleParty", node_class=CiResponsibleParty)
    reference_systems = xmlmap.NodeListField(
        xpath="gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier", node_class=ReferenceSystem)

    md_data_identification = xmlmap.NodeField(xpath="gmd:identificationInfo/gmd:MD_DataIdentification",
                                              node_class=MdDataIdentification)
    sv_service_identification = xmlmap.NodeField(xpath="gmd:identificationInfo/gmd:SV_ServiceIdentification",
                                                 node_class=SvServiceIdentification)

    def get_model_class(self):
        if self.hierarchy_level == "service":
            self.model = "registry.ServiceMetadata"
        else:
            self.model = "registry.DatasetMetadata"
        return super().get_model_class()

    def get_field_dict(self):
        """Custom function to convert xml object to database model schema.

        :return: all attributes in db model structure
        :rtype: dict
        """
        field_dict = super().get_field_dict()
        if self.md_data_identification:
            field_dict["bounding_geometry"] = self.md_data_identification.get_bounding_geometry()
            field_dict.update(self.md_data_identification.get_field_dict())
            self.md_data_identification.get_spatial_res(field_dict=field_dict)
            self.md_data_identification.get_dataset_id(field_dict=field_dict)
            self.md_data_identification.get_date_stamp(field_dict=field_dict)
        elif self.sv_service_identification:
            field_dict["bounding_geometry"] = self.sv_service_identification.get_bounding_geometry()
            field_dict.update(self.sv_service_identification.get_field_dict())
            self.sv_service_identification.get_spatial_res(
                field_dict=field_dict)
            self.sv_service_identification.get_dataset_id(
                field_dict=field_dict)
            self.sv_service_identification.get_date_stamp(
                field_dict=field_dict)
        # no database field. So we drop it here.
        field_dict.pop("hierarchy_level", None)
        return field_dict


class WrappedIsoMetadata(xmlmap.XmlObject):
    """Helper class to parse wrapped IsoMetadata objects.

    This class is needed you want to parse GetRecordsResponse xml for example. There are 0..n ``gmd:MD_Metadata``
    nodes wrapped by a ``csw:GetRecordsResponse`` node.
    """
    ROOT_NAMESPACES = dict([("gmd", GMD_NAMESPACE)])

    iso_metadata = xmlmap.NodeListField(
        xpath="//gmd:MD_Metadata", node_class=MdMetadata)
