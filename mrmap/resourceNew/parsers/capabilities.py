import os

from eulxml import xmlmap
from django.apps import apps
from django.db import models
from django.core.exceptions import ImproperlyConfigured

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
        if not self.model:
            raise ImproperlyConfigured(f"you need to configure the model attribute on class "
                                       f"'{self.__class__.__name__}'.")
        if isinstance(self.model, str):
            app_label, model_name = self.model.split('.', 1)
            self.model = apps.get_model(app_label=app_label, model_name=model_name)
        elif not issubclass(self.model, models.Model):
            raise ImproperlyConfigured(f"the configured model attribute on class '{self.__class__.__name__}' "
                                       f"isn't from type models.Model")
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
                if (isinstance(self._fields.get(key), xmlmap.SimpleBooleanField) or
                    isinstance(self._fields.get(key), xmlmap.StringField))\
                        and getattr(self, key) is None:
                    # we don't append None values, cause if we construct a model with key=None and the db field don't
                    # allow Null values but has a default for Boolean or string the db will raise integrity errors.
                    continue
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


class OperationUrl(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.OperationUrl'

    method = xmlmap.StringField(xpath="name(..)")
    url = xmlmap.StringField(xpath=f"@{NS_WC}href']")
    operation = xmlmap.StringField(xpath="name(../../../..)")


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Keyword'

    keyword = xmlmap.StringField(xpath=f"text()")


class ServiceMetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.MetadataContact'

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
    model = 'resourceNew.MimeType'

    mime_type = xmlmap.StringField(xpath=".")


class Style(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Style'

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
    model = None  # todo
    type = xmlmap.StringField(xpath=f"@{NS_WC}name']")
    units = xmlmap.StringField(xpath=f"@{NS_WC}units']")
    if SERVICE_VERSION == "1.3.0":
        extent_xpath = "text()"
    else:
        # todo
        extent_xpath = f"{NS_WC}Extent']/@name=''"
    extent = xmlmap.StringField(xpath=extent_xpath)


class RemoteMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.RemoteMetadata'

    link = xmlmap.StringField(xpath=f"{NS_WC}OnlineResource']/@{NS_WC}href']")


class LayerMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.LayerMetadata'

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
    model = 'resourceNew.ServiceMetadata'

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


EDGE_COUNTER = 0
NODE_ID = "0"


class Layer(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Layer'
    is_leaf_node = False
    level = 0
    left = 0
    right = 0

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
    remote_metadata = xmlmap.NodeListField(xpath=f"{NS_WC}MetadataURL']", node_class=RemoteMetadata)

    def __str__(self):
        return self.identifier

    def __repr__(self):
        return f"({self.identifier} | {self.level} | {self.left}:{self.right})"

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


class ServiceType(DBModelConverterMixin, xmlmap.XmlObject):
    model = "resourceNew.ServiceType"
    name = xmlmap.StringField(xpath="name()")
    version = xmlmap.StringField(xpath=f"@{NS_WC}version']")

    def get_field_dict(self):
        """ Overwrites the default get_field_dict() cause the parsed name of the root element doesn't contains the right
            value for database. We need to parse again cause the root attribute contains different service type names
            as we store in our database.

        """
        dic = super().get_field_dict()
        name = dic.get("name")
        name = name.split("_", 1)[0].lower()
        if name == "wmt":
            name = "wms"
        dic.update({"name": name})
        return dic


class Service(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.Service'

    all_layers = None
    all_keywords = None
    all_mime_types = None
    all_layer_metadata = None

    service_type = xmlmap.NodeField(xpath=".", node_class=ServiceType)
    service_metadata = xmlmap.NodeField(xpath=f"{NS_WC}Service']", node_class=ServiceMetadata)
    root_layer = xmlmap.NodeField(xpath=f"{NS_WC}Capability']/{NS_WC}Layer']", node_class=Layer)
    operation_urls = xmlmap.NodeListField(xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP']"
                                                f"//{NS_WC}OnlineResource']",
                                          node_class=OperationUrl)
    # todo:
    remote_metadata = None

    def get_all_layers(self):
        if not self.all_layers:
            self.all_layers = self.root_layer.get_descendants()
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
            _all.extend(self.service_metadata.keywords)
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
                for remote_metadata in layer.remote_metadata:
                    _all.append(remote_metadata.mime_type)
            self.all_mime_types = _all
        return self.all_mime_types


import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()
# your imports, e.g. Django models
from resourceNew.models.service import Service as DbService


if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    import time

    start = time.time()
    parsed_service = xmlmap.load_xmlobject_from_file(filename=current_dir + '/../tests/test_data/dwd_wms_1.3.0.xml',
                                                     xmlclass=Service)
    print("parsing took: " + str(time.time() - start))

    start = time.time()
    registered_service = DbService.objects.create(parsed_service=parsed_service)
    print("persisting: " + str(time.time() - start))
    registered_service.delete()
