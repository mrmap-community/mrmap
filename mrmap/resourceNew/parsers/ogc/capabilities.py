from django.contrib.gis.geos import Polygon
from eulxml import xmlmap
from pathlib import Path

from resourceNew.parsers.exceptions import SemanticError
from resourceNew.parsers.mixins import DBModelConverterMixin
from resourceNew.parsers.consts import NS_WC, IF_THEN_ELSE
from resourceNew.enums.service import OGCServiceEnum, OGCServiceVersionEnum


class MimeType(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.MimeType'

    mime_type = xmlmap.StringField(xpath=".")


class OperationUrl(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.OperationUrl'
    url = xmlmap.StringField(xpath=f"@{NS_WC}href']")

    def get_field_dict(self):
        dic = super().get_field_dict()
        method = dic.get("method", None)
        if method and ":" in method:
            dic.update({"method": method.rsplit(":", 1)[-1]})
        return dic


class WmsOperationUrl(OperationUrl):
    method = xmlmap.StringField(xpath="name(..)")
    operation = xmlmap.StringField(xpath="name(../../../..)")
    mime_types = xmlmap.NodeListField(xpath=f"../../../../{NS_WC}Format']", node_class=MimeType)


class WfsOperationUrl(OperationUrl):
    method = xmlmap.StringField(xpath="name(.)")
    operation = xmlmap.StringField(xpath=f"../../../@{NS_WC}name']")
    mime_types = xmlmap.NodeListField(
        xpath=f"../../../{NS_WC}Parameter'][@name='AcceptFormats' or @name='outputFormat' or @name='inputFormat']/{NS_WC}AllowedValues']/{NS_WC}Value']",
        node_class=MimeType)


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Keyword'

    keyword = xmlmap.StringField(xpath=f"text()")


class ServiceMetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
    """
        for wfs xpath route: wfs:WFS_Capabilities/ows:ServiceIdentification
        for wms xpath route: WMS_Capabilities/Service
    """
    model = 'resourceNew.MetadataContact'

    name = xmlmap.StringField(xpath=f"{NS_WC}ContactPersonPrimary']/{NS_WC}ContactOrganization']|{NS_WC}ProviderName']")
    person_name = xmlmap.StringField(
        xpath=f"{NS_WC}ContactPersonPrimary']/{NS_WC}ContactPerson']|{NS_WC}ServiceContact']/{NS_WC}IndividualName']")
    phone = xmlmap.StringField(
        xpath=f"{NS_WC}ContactVoiceTelephone']|{NS_WC}ContactInfo']/{NS_WC}Phone']/{NS_WC}Voice']")
    facsimile = xmlmap.StringField(
        xpath=f"{NS_WC}ContactFacsimileTelephone']|{NS_WC}ContactInfo']/{NS_WC}Phone']/{NS_WC}Facsimile']")
    email = xmlmap.StringField(
        xpath=f"{NS_WC}ContactElectronicMailAddress']|{NS_WC}ContactInfo']/{NS_WC}Address']/{NS_WC}ElectronicMailAddress']")
    country = xmlmap.StringField(
        xpath=f"{NS_WC}ContactAddress']/{NS_WC}Country']|{NS_WC}ContactInfo']/{NS_WC}Address']/{NS_WC}Country']")
    postal_code = xmlmap.StringField(
        xpath=f"{NS_WC}ContactAddress']/{NS_WC}PostCode']|{NS_WC}ContactInfo']/{NS_WC}Address']/{NS_WC}PostalCode']")
    city = xmlmap.StringField(
        xpath=f"{NS_WC}ContactAddress']/{NS_WC}City']|{NS_WC}ContactInfo']/{NS_WC}Address']/{NS_WC}City']")
    state_or_province = xmlmap.StringField(
        xpath=f"{NS_WC}ContactAddress']/{NS_WC}StateOrProvince']|{NS_WC}ContactInfo']/{NS_WC}Address']/{NS_WC}AdministrativeArea']")
    address = xmlmap.StringField(
        xpath=f"{NS_WC}ContactAddress']/{NS_WC}Address']|{NS_WC}ContactInfo']/{NS_WC}Address']/{NS_WC}DeliveryPoint']")


class LegendUrl(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.LegendUrl'

    legend_url = xmlmap.StringField(xpath=f"{NS_WC}OnlineResource']/@{NS_WC}href']")
    height = xmlmap.IntegerField(xpath=f"@{NS_WC}height']")
    width = xmlmap.IntegerField(xpath=f"@{NS_WC}width']")
    mime_type = xmlmap.NodeField(xpath=f"{NS_WC}Format']", node_class=MimeType)


class Style(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Style'

    name = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    legend_url = xmlmap.NodeField(xpath=f"{NS_WC}LegendURL']", node_class=LegendUrl)


class ReferenceSystem(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.ReferenceSystem"

    ref_system = xmlmap.StringField(xpath=".")

    def get_field_dict(self):
        dic = super().get_field_dict()

        ref_system = dic.get("ref_system", None)
        if "::" in ref_system:
            # example: ref_system = urn:ogc:def:crs:EPSG::4326
            code = ref_system.rsplit(":")[-1]
            prefix = ref_system.rsplit(":")[-3]
        elif ":" in ref_system:
            # example: ref_system = EPSG:4326
            code = ref_system.rsplit(":")[-1]
            prefix = ref_system.rsplit(":")[-2]
        else:
            raise SemanticError("reference system unknown")
        dic.update({"code": code,
                    "prefix": prefix})
        del dic["ref_system"]
        return dic


class Dimension(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.Dimension"

    name = xmlmap.StringField(xpath=f"@{NS_WC}name']")
    units = xmlmap.StringField(xpath=f"@{NS_WC}units']")

    # todo: xpath
    extent = xmlmap.StringField(xpath=f"{NS_WC}Extent']/@name=''")


class Dimension130(Dimension):
    extent = xmlmap.StringField(xpath="text()")


class RemoteMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.RemoteMetadata'

    link = xmlmap.StringField(xpath=f"{NS_WC}OnlineResource']/@{NS_WC}href']|@{NS_WC}href']")


class ServiceElementMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    abstract = xmlmap.StringField(xpath=f"{NS_WC}Abstract']")

    # ManyToManyField
    keywords = xmlmap.NodeListField(xpath=f"{NS_WC}KeywordList']/{NS_WC}Keyword']|{NS_WC}Keywords']/{NS_WC}Keyword']",
                                    node_class=Keyword)


class LayerMetadata(ServiceElementMetadata):
    model = 'resourceNew.LayerMetadata'


class FeatureTypeMetadata(ServiceElementMetadata):
    model = 'resourceNew.FeatureTypeMetadata'


class ServiceMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.ServiceMetadata'

    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    abstract = xmlmap.StringField(xpath=f"{NS_WC}Abstract']")
    fees = xmlmap.StringField(xpath=f"{NS_WC}Fees']")
    access_constraints = xmlmap.StringField(xpath=f"{NS_WC}AccessConstraints']")

    # ForeignKey
    service_contact = xmlmap.NodeField(xpath=f"{NS_WC}ContactInformation']|../{NS_WC}ServiceProvider']",
                                       node_class=ServiceMetadataContact)

    # ManyToManyField
    keywords = xmlmap.NodeListField(xpath=f"{NS_WC}KeywordList']/{NS_WC}Keyword']|{NS_WC}Keywords']/{NS_WC}Keyword']",
                                    node_class=Keyword)


EDGE_COUNTER = 0


class Layer111(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Layer'

    is_leaf_node = False
    level = 0
    left = 0
    right = 0

    scale_min = xmlmap.FloatField(xpath=f"{NS_WC}ScaleHint']/@{NS_WC}min']|{NS_WC}MinScaleDenominator']")
    scale_max = xmlmap.FloatField(xpath=f"{NS_WC}ScaleHint']/@{NS_WC}max']|{NS_WC}MaxScaleDenominator']")
    bbox_min_x = xmlmap.FloatField(
        xpath=f"{NS_WC}LatLonBoundingBox']/@{NS_WC}minx']|{NS_WC}EX_GeographicBoundingBox']/{NS_WC}westBoundLongitude']")
    bbox_max_x = xmlmap.FloatField(
        xpath=f"{NS_WC}LatLonBoundingBox']/@{NS_WC}maxx']|{NS_WC}EX_GeographicBoundingBox']/{NS_WC}eastBoundLongitude']")
    bbox_min_y = xmlmap.FloatField(
        xpath=f"{NS_WC}LatLonBoundingBox']/@{NS_WC}miny']|{NS_WC}EX_GeographicBoundingBox']/{NS_WC}southBoundLatitude']")
    bbox_max_y = xmlmap.FloatField(
        xpath=f"{NS_WC}LatLonBoundingBox']/@{NS_WC}maxy']|{NS_WC}EX_GeographicBoundingBox']/{NS_WC}northBoundLatitude']")
    reference_systems = xmlmap.NodeListField(xpath=f"{NS_WC}SRS']|{NS_WC}CRS']", node_class=ReferenceSystem)
    identifier = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    styles = xmlmap.NodeListField(xpath=f"{NS_WC}Style']", node_class=Style)
    is_queryable = xmlmap.SimpleBooleanField(xpath=f"@{NS_WC}queryable']", true=1, false=0)
    is_opaque = xmlmap.SimpleBooleanField(xpath=f"@{NS_WC}opaque']", true=1, false=0)
    is_cascaded = xmlmap.SimpleBooleanField(xpath=f"@{NS_WC}cascaded']", true=1, false=0)
    parent = xmlmap.NodeField(xpath=f"../../{NS_WC}Layer']", node_class="self")
    children = xmlmap.NodeListField(xpath=f"{NS_WC}Layer']", node_class="self")
    metadata = xmlmap.NodeField(xpath=".", node_class=LayerMetadata)
    remote_metadata = xmlmap.NodeListField(xpath=f"{NS_WC}MetadataURL']", node_class=RemoteMetadata)
    dimensions = xmlmap.NodeListField(xpath=f"{NS_WC}Dimension']", node_class=Dimension)

    def get_field_dict(self):
        dic = super().get_field_dict()
        # there is no default xmlmap field which parses to a geos polygon. So we convert it here.
        min_x = dic.get('bbox_min_x')
        max_x = dic.get('bbox_max_x')
        min_y = dic.get('bbox_min_y')
        max_y = dic.get('bbox_max_y')
        del dic['bbox_min_x'], dic['bbox_max_x'], dic['bbox_min_y'], dic['bbox_max_y']
        if min_x and max_x and min_y and max_y:
            bbox_lat_lon = Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y)))
            dic.update({"bbox_lat_lon": bbox_lat_lon})
        return dic

    def get_descendants(self, include_self=True, level=0):
        global EDGE_COUNTER
        EDGE_COUNTER += 1
        self.left = EDGE_COUNTER

        self.level = level

        descendants = []

        if self.children:
            level += 1
            for layer in self.children:
                descendants.extend(layer.get_descendants(level=level))
        else:
            self.is_leaf_node = True

        EDGE_COUNTER += 1
        self.right = EDGE_COUNTER

        if include_self:
            descendants.insert(0, self)

        return descendants


class Layer110(Layer111):
    # wms 1.1.0 supports whitelist spacing of srs. There is no default split function way in xpath 1.0
    # todo: try to use f"{NS_WC}SRS/tokenize(.," ")']"
    reference_systems = xmlmap.NodeListField(xpath=f"{NS_WC}SRS']", node_class=ReferenceSystem)


class Layer130(Layer111):
    dimensions = xmlmap.NodeListField(xpath=f"{NS_WC}Dimension']", node_class=Dimension130)


class FeatureType(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.FeatureType"
    identifier = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    metadata = xmlmap.NodeField(xpath=".", node_class=FeatureTypeMetadata)
    remote_metadata = xmlmap.NodeListField(xpath=f"{NS_WC}MetadataURL']", node_class=RemoteMetadata)
    bbox_lower_corner = xmlmap.StringField(xpath=f"{NS_WC}WGS84BoundingBox']/{NS_WC}LowerCorner']")
    bbox_upper_corner = xmlmap.StringField(xpath=f"{NS_WC}WGS84BoundingBox']/{NS_WC}UpperCorner']")
    output_formats = xmlmap.NodeListField(xpath=f"{NS_WC}OutputFormats']/{NS_WC}Format']", node_class=MimeType)
    reference_systems = xmlmap.NodeListField(
        xpath=f"{NS_WC}DefaultSRS']|{NS_WC}OtherSRS']|{NS_WC}DefaultCRS']|{NS_WC}OtherCRS']",
        node_class=ReferenceSystem)

    def get_field_dict(self):
        dic = super().get_field_dict()
        # there is no default xmlmap field which parses to a geos polygon. So we convert it here.
        bbox_lower_corner = dic.get('bbox_lower_corner', None)
        bbox_upper_corner = dic.get('bbox_upper_corner', None)

        if bbox_lower_corner and bbox_upper_corner:
            min_x = float(bbox_lower_corner.split(" ")[0])
            min_y = float(bbox_lower_corner.split(" ")[1])
            max_x = float(bbox_upper_corner.split(" ")[0])
            max_y = float(bbox_upper_corner.split(" ")[1])

            bbox_lat_lon = Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y)))
            dic.update({"bbox_lat_lon": bbox_lat_lon})

        del dic['bbox_lower_corner'], dic['bbox_upper_corner']

        return dic


class ServiceType(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.ServiceType"

    wms_name = xmlmap.StringField(xpath=f"{NS_WC}Service']/{NS_WC}Name']")
    wfs_name = xmlmap.StringField(xpath=f"{NS_WC}ServiceIdentification']/{NS_WC}ServiceType']")
    version = xmlmap.StringField(xpath=f"@{NS_WC}version']")

    def get_field_dict(self):
        """ Overwrites the default get_field_dict() cause the parsed name of the root element doesn't contains the right
            value for database. We need to parse again cause the root attribute contains different service type names
            as we store in our database.

            Returns:
                field_dict (dict): the dict which contains all needed information

            Raises:
                SemanticError if service name or version can not be found
        """
        dic = super().get_field_dict()
        if dic.get("wms_name", None):
            name = dic.get("wms_name").lower()
        elif dic.get("wfs_name", None):
            name = dic.get("wfs_name").lower()
        else:
            raise SemanticError("could not determine the service type for the parsed capabilities document.")

        del dic["wms_name"], dic["wfs_name"]

        if ":" in name:
            name = name.split(":", 1)[-1]
        elif " " in name:
            name = name.split(" ", 1)[-1]

        if name not in ["wms", "wfs"]:
            raise SemanticError(f"could not determine the service type for the parsed capabilities document. "
                                f"Parsed name was {name}")
        dic.update({"name": name})

        return dic


class Service(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Service'
    # todo: new field with node_class RemoteMetadata for wms and wfs
    remote_metadata = None


class WmsService(Service):
    all_layers = None
    service_type = xmlmap.NodeField(xpath=".", node_class=ServiceType)
    service_metadata = xmlmap.NodeField(xpath=f"{NS_WC}Service']", node_class=ServiceMetadata)
    operation_urls = xmlmap.NodeListField(xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP']"
                                                f"//{NS_WC}OnlineResource']",
                                          node_class=WmsOperationUrl)

    def get_all_layers(self):
        if not self.all_layers:
            self.all_layers = self.root_layer.get_descendants()
        return self.all_layers


class Wms110Service(WmsService):
    root_layer = xmlmap.NodeField(xpath=f"{NS_WC}Capability']/{NS_WC}Layer']", node_class=Layer110)


class Wms111Service(WmsService):
    root_layer = xmlmap.NodeField(xpath=f"{NS_WC}Capability']/{NS_WC}Layer']", node_class=Layer111)


class Wms130Service(WmsService):
    root_layer = xmlmap.NodeField(xpath=f"{NS_WC}Capability']/{NS_WC}Layer']", node_class=Layer130)


class Wfs200Service(Service):
    service_type = xmlmap.NodeField(xpath=".", node_class=ServiceType)
    service_metadata = xmlmap.NodeField(xpath=f"{NS_WC}ServiceIdentification']", node_class=ServiceMetadata)
    operation_urls = xmlmap.NodeListField(
        xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP'] //{NS_WC}OnlineResource'] |"
              f"{NS_WC}OperationsMetadata']/{NS_WC}Operation']//{NS_WC}DCP']/{NS_WC}HTTP']/*",
        node_class=WfsOperationUrl)
    feature_types = xmlmap.NodeListField(xpath=f"{NS_WC}FeatureTypeList']//{NS_WC}FeatureType']",
                                         node_class=FeatureType)


def get_parsed_service(xml):
    """ helper function to construct the right base parser class

    """
    if isinstance(xml, str) or isinstance(xml, bytes):
        load_func = xmlmap.load_xmlobject_from_string
    elif isinstance(xml, Path):
        xml = xml.resolve().__str__()
        load_func = xmlmap.load_xmlobject_from_file
    else:
        raise ValueError("xml must be ether a str or Path")

    xml_class = None
    service_type = load_func(xml,
                             xmlclass=ServiceType)
    service_type_dict = service_type.get_field_dict()
    if service_type_dict['name'] == OGCServiceEnum.WMS.value:
        if service_type_dict["version"] == OGCServiceVersionEnum.V_1_1_0.value:
            xml_class = Wms110Service
        elif service_type_dict["version"] == OGCServiceVersionEnum.V_1_1_1.value:
            xml_class = Wms111Service
        elif service_type_dict["version"] == OGCServiceVersionEnum.V_1_3_0.value:
            xml_class = Wms130Service
    elif service_type_dict['name'] == OGCServiceEnum.WFS.value:
        if service_type_dict["version"] == OGCServiceVersionEnum.V_1_0_0.value:
            xml_class = Wfs200Service
        elif service_type_dict["version"] == OGCServiceVersionEnum.V_1_1_0.value:
            xml_class = Wfs200Service
        elif service_type_dict["version"] == OGCServiceVersionEnum.V_1_3_0.value:
            xml_class = Wfs200Service
        elif service_type_dict["version"] == OGCServiceVersionEnum.V_2_0_0.value:
            xml_class = Wfs200Service
        elif service_type_dict["version"] == OGCServiceVersionEnum.V_2_0_2.value:
            xml_class = Wfs200Service

    if not xml_class:
        raise NotImplementedError(f"unsupported service type `{service_type_dict['name']}` with version "
                                  f"`{service_type_dict['version']}` detected.")

    parsed_service = load_func(xml,
                               xmlclass=xml_class)
    return parsed_service
