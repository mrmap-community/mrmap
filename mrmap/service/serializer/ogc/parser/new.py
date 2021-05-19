import os

from eulxml import xmlmap
from django.apps import apps
from django.db import models


NS_WC = "*[local-name()='"  # Namespace wildcard
SERVICE_VERSION = "1.3.0"


class DBModelConverterMixin:
    model = None
    db_obj = None

    def get_model_class(self):
        """ Return the configured model class. If model class is named as string like 'app_label.model_cls_name', the
            model will be resolved by the given string. If the model class is directly configured by do not lookup by
            string.

        Returns:
            self.model (Django Model class)
        """
        if isinstance(self.model, str):
            app_label, model_name = self.model.split('.', 1)
            return apps.get_model(app_label=app_label, model_name=model_name)
        elif issubclass(self.model, models.Model):
            return self.model

    def get_field_dict(self):
        """ Return a dict which contains the key, value pairs of the given field attribute name as key and the
            attribute value it self as value.

            Examples:
                If the following two classes are given:

                class Nested(DBModelConverterMixin, xmlmap.XmlObject):
                    ...

                class SomeXmlObject(DBModelConverterMixin, xmlmap.XmlObject):
                    name = xmlmap.StringField('name')
                    nested = xmlmap.NodeField('nested', Nested)
                    nested_list = xmlmap.NodeListField('nested', Nested)

                The SomeXmlObject().get_field_dict() function return {'name': 'Something'}

        Returns:
            field_dict (dict): the dict which contains all simple fields of the object it self.

        """
        field_dict = {}
        for key in self._fields.keys():
            if not isinstance(self._fields.get(key), xmlmap.NodeField) and \
                    not isinstance(self._fields.get(key), xmlmap.NodeListField):
                field_dict.update({key: getattr(self, key)})
        return field_dict

    def get_node_field_dict(self):
        """ Return a dict which contains the key, value pairs of the given field attribute name as key and the
            referenced object it self as value.

            Examples:
                If the following two classes are given:

                class Nested(DBModelConverterMixin, xmlmap.XmlObject):
                    ...

                class SomeXmlObject(DBModelConverterMixin, xmlmap.XmlObject):
                    name = xmlmap.StringField('name')
                    nested = xmlmap.NodeField('nested', Nested)
                    nested_list = xmlmap.NodeListField('nested', Nested)

                The SomeXmlObject().get_node_field_dict() function return {'nested': NestedInstance}

        Returns:
            node_field_dict (dict): the dict which contains all fields which are referencing to one other object.

        """
        node_field_dict = {}
        for key in self._fields.keys():
            if isinstance(self._fields.get(key), xmlmap.NodeField):
                node_field_dict.update({key: getattr(self, key)})
        return node_field_dict

    def get_list_field_dict(self):
        """ Return a dict which contains the key, value pairs of the given field attribute name as key and the
            referenced objects list as value.

            Examples:
                If the following two classes are given:

                class Nested(DBModelConverterMixin, xmlmap.XmlObject):
                    ...

                class SomeXmlObject(DBModelConverterMixin, xmlmap.XmlObject):
                    name = xmlmap.StringField('name')
                    nested = xmlmap.NodeField('nested', Nested)
                    nested_list = xmlmap.NodeListField('nested', Nested)

                The SomeXmlObject().get_related_field_dict() function return {'nested_list': [NestedInstance1, ...]}

        Returns:
            list_field_dict (dict): the dict which contains all fields which are lists of referenced other objects.

        """
        list_field_dict = {}
        for key in self._fields.keys():
            if isinstance(self._fields.get(key), xmlmap.NodeListField):
                list_field_dict.update({key: getattr(self, key)})
        return list_field_dict

    def get_db_model_instance(self):
        """ Lookup the configured model, where this xmlobject shall be transformed to, construct it with the parsed
            attributes and returns it. The constructed model instance will also be available by the self.db_obj
            attribute.

        Returns:
            self.db_obj (Django model instance): The constructed **not persisted** django model instance.
        """
        if not self.db_obj:
            self.db_obj = self.get_model_class()(**self.get_field_dict())
        return self.db_obj


class ServiceUrl(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.ServiceUrl'

    method = xmlmap.StringField(xpath="name(..)")
    url = xmlmap.StringField(xpath=f"{NS_WC}href']")
    operation = xmlmap.StringField(xpath="name(../../../..)")


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Keyword'

    keyword = xmlmap.StringField(xpath=f"text()")


class ServiceMetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'structure.Organization'

    name = xmlmap.StringField(xpath=f"{NS_WC}ContactPersonPrimary']/{NS_WC}ContactOrganization']")
    person_name = xmlmap.StringField(xpath=f"{NS_WC}ContactPersonPrimary']/{NS_WC}ContactPerson']")
    phone = xmlmap.StringField(xpath=f"{NS_WC}ContactVoiceTelephone']")
    facsimile = xmlmap.StringField(xpath=f"{NS_WC}ContactFacsimileTelephone']")
    email = xmlmap.StringField(xpath=f"{NS_WC}ContactElectronicMailAddress']")
    country = xmlmap.StringField(xpath=f"{NS_WC}ContactAddress']/{NS_WC}Country']")
    postal_code = xmlmap.StringField(xpath=f"{NS_WC}ContactAddress']/{NS_WC}PostCode']")
    city = xmlmap.StringField(xpath=f"{NS_WC}ContactAddress']/{NS_WC}City']")
    state_or_province = xmlmap.StringField(xpath=f"{NS_WC}ContactAddress']/{NS_WC}StateOrProvince']")
    address = xmlmap.StringField(xpath=f"{NS_WC}ContactAddress']/{NS_WC}Address']")


class MimeType(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.MimeType'

    mime_type = xmlmap.StringField(xpath=".")


class Style(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Style'

    name = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    legend_uri = xmlmap.StringField(xpath=f"{NS_WC}LegendURL']/{NS_WC}OnlineResource']/@{NS_WC}href']")
    height = xmlmap.IntegerField(xpath=f"{NS_WC}LegendURL']/@{NS_WC}height']")
    width = xmlmap.IntegerField(xpath=f"{NS_WC}LegendURL']/@{NS_WC}width']")
    # todo: manytomany possible for mime types?
    mime_type = xmlmap.NodeField(xpath=f"{NS_WC}LegendURL']/{NS_WC}Format']", node_class=MimeType)


class ReferenceSystem(DBModelConverterMixin, xmlmap.XmlObject):
    # todo
    code = None
    prefix = None


class Dimension(DBModelConverterMixin, xmlmap.XmlObject):
    type = xmlmap.StringField(xpath=f"@{NS_WC}name']")
    units = xmlmap.StringField(xpath=f"@{NS_WC}units']")
    if SERVICE_VERSION == "1.3.0":
        extent_xpath = "text()"
    else:
        # todo
        extent_xpath = f"{NS_WC}Extent']/@name=''"
    extent = xmlmap.StringField(xpath=extent_xpath)


class DatasetMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    # todo: manytomany possible for mime types?
    mime_type = xmlmap.NodeField(xpath=f"{NS_WC}Format']", node_class=MimeType)
    online_resource = xmlmap.StringField(xpath=f"{NS_WC}OnlineResource']/@{NS_WC}href']")


class LayerMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'metadata.LayerMetadata'

    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    abstract = xmlmap.StringField(xpath=f"{NS_WC}Abstract']")

    # ManyToManyField
    keywords = xmlmap.NodeListField(xpath=f"{NS_WC}KeywordList']/{NS_WC}Keyword']", node_class=Keyword)
    if SERVICE_VERSION == "1.3.0":
        reference_systems_xpath = f"{NS_WC}CRS']"
    else:
        reference_systems_xpath = f"{NS_WC}SRS']"
    reference_systems = xmlmap.NodeListField(xpath=reference_systems_xpath, node_class=ReferenceSystem)
    dimensions = xmlmap.NodeListField(xpath=f"{NS_WC}Dimension']", node_class=Dimension)


class ServiceMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'metadata.ServiceMetadata'

    identifier = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    title = xmlmap.StringField(xpath=f"{NS_WC}Title']")
    abstract = xmlmap.StringField(xpath=f"{NS_WC}Abstract']")
    fees = xmlmap.StringField(xpath=f"{NS_WC}Fees']")
    access_constraints = xmlmap.StringField(xpath=f"{NS_WC}AccessConstraints']")
    online_resource = xmlmap.StringField(xpath=f"{NS_WC}OnlineResource']/@{NS_WC}href']")

    # ForeignKey
    contact = xmlmap.NodeField(xpath=f"{NS_WC}ContactInformation']", node_class=ServiceMetadataContact)

    # ManyToManyField
    keywords = xmlmap.NodeListField(xpath=f"{NS_WC}KeywordList']/{NS_WC}Keyword']", node_class=Keyword)


class Layer(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Layer'

    identifier = xmlmap.StringField(xpath=f"{NS_WC}Name']")
    styles = xmlmap.NodeListField(xpath=f"{NS_WC}Style']", node_class=Style)
    scale_min = xmlmap.IntegerField(xpath=f"{NS_WC}ScaleHint']/@{NS_WC}min']")
    scale_max = xmlmap.IntegerField(xpath=f"{NS_WC}ScaleHint']/@{NS_WC}max']")

    # todo: implement custom xmlmap.PolygonField().. current parsing:
    """
    <EX_GeographicBoundingBox>
        <westBoundLongitude>-180.0</westBoundLongitude>
        <eastBoundLongitude>180.0</eastBoundLongitude>
        <southBoundLatitude>-90.0</southBoundLatitude>
        <northBoundLatitude>90.0</northBoundLatitude>
    </EX_GeographicBoundingBox>
    bbox = xml_helper.try_get_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("EX_GeographicBoundingBox"),
            layer_xml)[0]
        attrs = {
            "westBoundLongitude": "minx",
            "eastBoundLongitude": "maxx",
            "southBoundLatitude": "miny",
            "northBoundLatitude": "maxy",
        }
        for key, val in attrs.items():
            tmp = xml_helper.try_get_text_from_xml_element(
                xml_elem=bbox,
                elem="./" + GENERIC_NAMESPACE_TEMPLATE.format(key)
            )
            if tmp is None:
                tmp = 0
            layer_obj.capability_bbox_lat_lon[val] = tmp
    bounding_points = (
            (float(self.capability_bbox_lat_lon["minx"]), float(self.capability_bbox_lat_lon["miny"])),
            (float(self.capability_bbox_lat_lon["minx"]), float(self.capability_bbox_lat_lon["maxy"])),
            (float(self.capability_bbox_lat_lon["maxx"]), float(self.capability_bbox_lat_lon["maxy"])),
            (float(self.capability_bbox_lat_lon["maxx"]), float(self.capability_bbox_lat_lon["miny"])),
            (float(self.capability_bbox_lat_lon["minx"]), float(self.capability_bbox_lat_lon["miny"]))
        )
    metadata.bounding_geometry = Polygon(bounding_points)
    """
    bbox_lat_lon = None

    # todo: SimpleBooleanField does not support multiple false values such as None and 0 shall interpreted as False
    is_queryable = xmlmap.SimpleBooleanField(xpath=f"@{NS_WC}queryable']", true=1, false=0)
    is_opaque = xmlmap.SimpleBooleanField(xpath=f"@{NS_WC}opaque']", true=1, false=0)
    is_cascaded = xmlmap.SimpleBooleanField(xpath=f"@{NS_WC}cascaded']", true=1, false=0)

    # ForeignKey/OneToOneField
    parent = xmlmap.NodeField(xpath=f"../../{NS_WC}Layer']", node_class="self")
    children = xmlmap.NodeListField(xpath=f"{NS_WC}Layer']", node_class="self")
    layer_metadata = xmlmap.NodeField(xpath=".", node_class=LayerMetadata)
    dataset_metadata = xmlmap.NodeListField(xpath=f"{NS_WC}MetadataURL']", node_class=DatasetMetadata)

    def get_descendants(self, include_self=False):
        descendants = []
        if self.children:
            for layer in self.children:
                descendants.extend(layer.get_descendants())
        else:
            descendants.append(self)

        if include_self:
            descendants.append(self)

        return descendants


class ServiceType(DBModelConverterMixin, xmlmap.XmlObject):
    version = xmlmap.StringField(xpath=f"@{NS_WC}version']")


class Service(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Service'

    all_layers = None
    all_keywords = None
    all_mime_types = None
    all_layer_metadata = None

    service_type = xmlmap.NodeField(xpath=".", node_class=ServiceType)
    service_metadata = xmlmap.NodeField(xpath=f"{NS_WC}Service']", node_class=ServiceMetadata)
    root_layer = xmlmap.NodeField(xpath=f"{NS_WC}Capability']/{NS_WC}Layer']", node_class=Layer)
    service_urls = xmlmap.NodeListField(xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP']//{NS_WC}OnlineResource']",
                                        node_class=ServiceUrl)

    def get_all_layers(self):
        if not self.all_layers:
            self.all_layers = self.root_layer.get_descendants(include_self=True)
        return self.all_layers

    def get_all_layer_metadata(self):
        if not self.all_layer_metadata:
            _all = []
            for layer in self.get_all_layers():
                _all.append(layer.layer_metadata)
            self.all_layer_metadata = _all
        return self.all_layer_metadata

    def get_all_keywords(self) -> list:
        """
            Returns:
                list: all keywords which are parsed in the whole service
        """
        if not self.all_keywords:
            _all = []
            _all.extend(self.metadata.keywords)
            for layer in self.get_all_layers():
                _all.extend(layer.layer_metadata.keywords)
            self.all_keywords = _all
        return self.all_keywords

    def get_all_mime_types(self) -> list:
        """
            Returns:
                list: all mime_types which are parsed in the whole service
        """
        if not self.all_mime_types:
            _all = []
            for layer in self.get_all_layers():
                for style in layer.styles:
                    _all.append(style.mime_type)
                for dataset in layer.dataset_metadata:
                    _all.append(dataset.mime_type)
            self.all_mime_types = _all
        return self.all_mime_types


if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    xml_obj = xmlmap.load_xmlobject_from_file(filename=current_dir + '/dwd_wms_1.3.0.xml', xmlclass=Service)

    print(xml_obj.node)
