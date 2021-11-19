from django.utils import timezone
from django.contrib.gis.geos import Polygon
from eulxml import xmlmap
from pathlib import Path
from isodate.isodatetime import parse_datetime
from isodate.isoduration import parse_duration
from isodate.isodates import parse_date
from isodate.isoerror import ISO8601Error
from isodate.duration import Duration
from registry.xmlmapper.exceptions import SemanticError
from registry.xmlmapper.mixins import DBModelConverterMixin
from registry.xmlmapper.consts import NS_WC
from registry.enums.service import OGCServiceEnum, OGCServiceVersionEnum
from django.conf import settings


class XlinkHref(xmlmap.XmlObject):
    url = xmlmap.StringField(xpath="@xlink:href")


class MimeType(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'registry.MimeType'

    mime_type = xmlmap.StringField(xpath=".")


class OperationUrl(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'registry.OperationUrl'
    url = xmlmap.StringField(xpath="@xlink:href")

    def get_field_dict(self):
        dic = super().get_field_dict()
        method = dic.get("method", None)
        if method and ":" in method:
            dic.update({"method": method.rsplit(":", 1)[-1]})
        # This removes the (non-standard) map-Parameter required by MapServer, e.g.
        # https://gis.mffjiv.rlp.de/cgi-bin/mapserv?map=/data/mapserver/mapfiles/institutions_0601.map&amp;
        # *** This would break all requests to the mapserver instance! ***
        # if url:
        #     dic.update({"url": url.split("?", 1)[0]})
        return dic


class WmsOperationUrl(OperationUrl):
    method = xmlmap.StringField(xpath="name(..)")
    operation = xmlmap.StringField(xpath="name(../../../..)")
    mime_types = xmlmap.NodeListField(xpath=f"../../../../{NS_WC}Format']", node_class=MimeType)


class WfsCswOperationUrl(OperationUrl):
    method = xmlmap.StringField(xpath="name(.)")
    operation = xmlmap.StringField(xpath=f"../../../@{NS_WC}name']")
    mime_types = xmlmap.NodeListField(
        xpath=f"../../../{NS_WC}Parameter'][@name='AcceptFormats' or @name='outputFormat' or @name='inputFormat']/{NS_WC}AllowedValues']/{NS_WC}Value']",
        node_class=MimeType)


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'registry.Keyword'

    keyword = xmlmap.StringField(xpath="text()")


class ServiceMetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
    """
        for wfs xpath route: wfs:WFS_Capabilities/ows:ServiceIdentification
        for wms xpath route: WMS_Capabilities/Service
    """
    model = 'registry.MetadataContact'

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
    model = 'registry.LegendUrl'

    legend_url = xmlmap.NodeField(xpath=f"{NS_WC}OnlineResource']", node_class=XlinkHref)
    height = xmlmap.IntegerField(xpath=f"@{NS_WC}height']")
    width = xmlmap.IntegerField(xpath=f"@{NS_WC}width']")
    mime_type = xmlmap.NodeField(xpath=f"{NS_WC}Format']", node_class=MimeType)


class Style(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'registry.Style'

    name = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    legend_url = xmlmap.NodeField(xpath=f"{NS_WC}LegendURL']", node_class=LegendUrl)


class ReferenceSystem(DBModelConverterMixin, xmlmap.XmlObject):
    model = "registry.ReferenceSystem"

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
                    "prefix": prefix.upper()})
        del dic["ref_system"]
        return dic


class TimeExtent(DBModelConverterMixin):
    model = "registry.TimeExtent"
    start = None
    stop = None
    resolution = None

    def __init__(self, start, stop, resolution=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start = start
        self.stop = stop
        self.resolution = resolution

    def get_field_dict(self):
        return {"start": self.start,
                "stop": self.stop,
                "resolution": self.resolution}


class Extent111(DBModelConverterMixin, xmlmap.XmlObject):
    name = xmlmap.StringField(xpath=f"@{NS_WC}name']")
    extent = xmlmap.StringField(xpath="text()")


class Dimension111(DBModelConverterMixin, xmlmap.XmlObject):
    model = "registry.Dimension"

    name = xmlmap.StringField(xpath=f"@{NS_WC}name']")
    units = xmlmap.StringField(xpath=f"@{NS_WC}units']")

    parsed_extent = None
    parsed_extents = xmlmap.NodeListField(xpath=f"../{NS_WC}Extent']", node_class=Extent111)
    extents = []

    def parse_extent_value(self, start, stop, resolution) -> tuple:
        _start = parse_datetime(start)  # iso date time
        _stop = parse_datetime(stop)  # iso date time
        try:
            _resolution = int(resolution)
        except ValueError:
            _resolution = parse_duration(resolution)
            if isinstance(_resolution, Duration):
                _resolution = _resolution.totimedelta(start=timezone.now())
        return _start, _stop, _resolution

    def parse_datetime_or_date(self, value):
        _value = None
        try:
            _value = parse_datetime(value)
        except ISO8601Error:
            try:
                _value = parse_date(value)
            except ISO8601Error:
                # todo: log this
                pass

        return _value

    def parse_extent(self):
        if hasattr(self, "parsed_extents"):
            try:
                parsed_extent = next(extent for extent in self.parsed_extents if extent.name == self.name)
                self.parsed_extent = parsed_extent.__str__()
            except StopIteration:
                self.parsed_extent = None

        if self.units == "ISO8601":
            if "," in self.parsed_extent and "/" in self.parsed_extent:
                # a list of interval values detected
                intervals = self.parsed_extent.split(",")
                for interval in intervals:
                    split = interval.split("/")
                    start, stop, resolution = self.parse_extent_value(start=split[0], stop=split[1], resolution=split[2])
                    self.extents.append(TimeExtent(start=start, stop=stop, resolution=resolution))
            elif "/" in self.parsed_extent:
                # one interval detected
                split = self.parsed_extent.split("/")
                start, stop, resolution = self.parse_extent_value(start=split[0], stop=split[1], resolution=split[2])
                self.extents.append(TimeExtent(start=start, stop=stop, resolution=resolution))
            elif "," in self.parsed_extent:
                # a list of single values detected
                split = self.parsed_extent.split(",")
                for value in split:
                    _value = self.parse_datetime_or_date(value)
                    if _value:
                        self.extents.append(TimeExtent(start=_value, stop=_value))
                    else:
                        settings.ROOT_LOGGER.error(msg=f"can't parse time dimension from value: {self.parsed_extent}")
            else:
                # one single value was detected
                _value = self.parse_datetime_or_date(self.parsed_extent)
                if _value:
                    self.extents.append(TimeExtent(start=_value, stop=_value))
                else:
                    settings.ROOT_LOGGER.error(msg=f"can't parse time dimension from value: {self.parsed_extent}")


class Dimension130(Dimension111):
    parsed_extent = xmlmap.StringField(xpath="text()")


class RemoteMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'registry.RemoteMetadata'

    link = xmlmap.StringField(xpath=f"{NS_WC}OnlineResource']/@{NS_WC}href']|@{NS_WC}href']")


class ServiceElementMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    abstract = xmlmap.StringField(xpath=f"{NS_WC}Abstract']")
    # ManyToManyField
    keywords = xmlmap.NodeListField(xpath=f"{NS_WC}KeywordList']/{NS_WC}Keyword']|{NS_WC}Keywords']/{NS_WC}Keyword']",
                                    node_class=Keyword)


class LayerMetadata(ServiceElementMetadata):
    model = 'registry.LayerMetadata'


class FeatureTypeMetadata(ServiceElementMetadata):
    model = 'registry.FeatureTypeMetadata'


class ServiceMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'registry.ServiceMetadata'

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
    model = 'registry.Layer'

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
    dimensions = xmlmap.NodeListField(xpath=f"{NS_WC}Dimension']", node_class=Dimension111)

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
    parent = xmlmap.NodeField(xpath=f"../../{NS_WC}Layer']", node_class="self")
    children = xmlmap.NodeListField(xpath=f"{NS_WC}Layer']", node_class="self")


class Layer130(Layer111):
    dimensions = xmlmap.NodeListField(xpath=f"{NS_WC}Dimension']", node_class=Dimension130)
    parent = xmlmap.NodeField(xpath=f"../../{NS_WC}Layer']", node_class="self")
    children = xmlmap.NodeListField(xpath=f"{NS_WC}Layer']", node_class="self")


class FeatureType(DBModelConverterMixin, xmlmap.XmlObject):
    model = "registry.FeatureType"
    identifier = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    metadata = xmlmap.NodeField(xpath=".", node_class=FeatureTypeMetadata)
    remote_metadata = xmlmap.NodeListField(xpath=f"{NS_WC}MetadataURL']", node_class=RemoteMetadata)
    bbox_lower_corner = xmlmap.StringField(xpath=f"{NS_WC}WGS84BoundingBox']/{NS_WC}LowerCorner']")
    bbox_upper_corner = xmlmap.StringField(xpath=f"{NS_WC}WGS84BoundingBox']/{NS_WC}UpperCorner']")
    output_formats = xmlmap.NodeListField(xpath=f"{NS_WC}OutputFormats']/{NS_WC}Format']", node_class=MimeType)
    reference_systems = xmlmap.NodeListField(
        xpath=f"{NS_WC}DefaultSRS']|{NS_WC}OtherSRS']|{NS_WC}DefaultCRS']|{NS_WC}OtherCRS']",
        node_class=ReferenceSystem)
    # todo: add dimensions

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
    model = "registry.ServiceType"

    wms_name = xmlmap.StringField(xpath=f"{NS_WC}Service']/{NS_WC}Name']")
    wfs_csw_name = xmlmap.StringField(xpath=f"{NS_WC}ServiceIdentification']/{NS_WC}ServiceType']")
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
        elif dic.get("wfs_csw_name", None):
            name = dic.get("wfs_csw_name").lower()
        else:
            raise SemanticError("could not determine the service type for the parsed capabilities document.")

        del dic["wms_name"], dic["wfs_csw_name"]

        if ":" in name:
            name = name.split(":", 1)[-1]
        elif " " in name:
            name = name.split(" ", 1)[-1]

        if name not in ["wms", "wfs", "csw"]:
            raise SemanticError(f"could not determine the service type for the parsed capabilities document. "
                                f"Parsed name was {name}")
        dic.update({"name": name})

        return dic


class Service(DBModelConverterMixin, xmlmap.XmlObject):
    # todo: new field with node_class RemoteMetadata for wms and wfs
    remote_metadata = None
    service_url = xmlmap.NodeField(xpath=f"//{NS_WC}Service']/{NS_WC}OnlineResource']", node_class=XlinkHref)
    version = xmlmap.StringField(xpath=f"@{NS_WC}version']")

    def get_field_dict(self):
        field_dict = super().get_field_dict()
        if self.url:
            field_dict.update({"url": self.url.url})
        return field_dict


class WmsService(Service):
    model = 'registry.WebMapService'

    all_layers = None
    # service_type = xmlmap.NodeField(xpath=".", node_class=ServiceType)
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
    model = 'registry.WebFeatureService'

    # service_type = xmlmap.NodeField(xpath=".", node_class=ServiceType)
    service_metadata = xmlmap.NodeField(xpath=f"{NS_WC}ServiceIdentification']", node_class=ServiceMetadata)
    operation_urls = xmlmap.NodeListField(
        xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP'] //{NS_WC}OnlineResource'] |"
              f"{NS_WC}OperationsMetadata']/{NS_WC}Operation']//{NS_WC}DCP']/{NS_WC}HTTP']/*",
        node_class=WfsCswOperationUrl)
    feature_types = xmlmap.NodeListField(xpath=f"{NS_WC}FeatureTypeList']//{NS_WC}FeatureType']",
                                         node_class=FeatureType)


class CswService(Service):
    model = 'registry.CatalougeService'

    # service_type = xmlmap.NodeField(xpath=".", node_class=ServiceType)
    service_metadata = xmlmap.NodeField(xpath=f"{NS_WC}ServiceIdentification']", node_class=ServiceMetadata)
    operation_urls = xmlmap.NodeListField(
        xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP'] //{NS_WC}OnlineResource'] |"
              f"{NS_WC}OperationsMetadata']/{NS_WC}Operation']//{NS_WC}DCP']/{NS_WC}HTTP']/*",
        node_class=WfsCswOperationUrl)


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
    elif service_type_dict['name'] == OGCServiceEnum.CSW.value:
        xml_class = CswService

    if not xml_class:
        raise NotImplementedError(f"unsupported service type `{service_type_dict['name']}` with version "
                                  f"`{service_type_dict['version']}` detected.")

    parsed_service = load_func(xml,
                               xmlclass=xml_class)
    return parsed_service
