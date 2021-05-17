import os

from eulxml import xmlmap
from django.apps import apps
from django.db import models

from service.helper.enums import HttpMethodEnum, OGCOperationEnum

NS_WC = "*[local-name()='{}']"



class DBModelConverterMixin:
    model = None

    def _get_model_class(self):
        if isinstance(self.model, str):
            app_label, model_name = self.model.split('.', 1)
            return apps.get_model(app_label=app_label, model_name=model_name)
        elif issubclass(self.model, models.Model):
            return self.model

    def get_field_dict(self):
        field_dict = {}
        for key in self._fields.keys():
            if not isinstance(self._fields.get(key), xmlmap.NodeField) and \
                    not isinstance(self._fields.get(key), xmlmap.NodeListField):
                field_dict.update({key: getattr(self, key)})
        return field_dict

    def get_related_field_dict(self):
        related_field_dict = {}
        for key in self._fields.keys():
            if isinstance(self._fields.get(key), xmlmap.NodeField):
                related_field_dict.update({key: getattr(self, key)})
        return related_field_dict

    def get_m2m_field_dict(self):
        m2m_field_dict = {}
        for key in self._fields.keys():
            if isinstance(self._fields.get(key), xmlmap.NodeListField):
                m2m_field_dict.update({key: getattr(self, key)})
        return m2m_field_dict

    def to_db_model(self):
        print(self.model)
        dic = self.get_field_dict()
        print(dic)
        return self._get_model_class()(**dic)

    def related_to_db_model(self):
        self_db_obj = self.to_db_model()
        print(self_db_obj)

        related_field_dict = self.get_related_field_dict()
        if related_field_dict:
            for key, related_object in related_field_dict.items():
                setattr(self_db_obj, key, related_object.related_to_db_model())

        return self_db_obj

    def traverse_related_db_models(self, db_model):
        for field in db_model._meta.fields:
            if field.get_internal_type() == 'ForeignKey' or field.get_internal_type() == 'OneToOneField':
                related_object = getattr(db_model, field.name)
                self.traverse_related_db_models(related_object)
                related_object.save()
        return

    def to_db(self):
        self_db_obj = self.related_to_db_model()
        self.traverse_related_db_models(self_db_obj)
        self_db_obj.save()

        # save m2m objects

        # add m2m objects to self
        pass


class ServiceUrl(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.ServiceUrl'
    method = xmlmap.StringField(xpath="name(..)")
    url = xmlmap.StringField(xpath="@*[local-name()='href']")
    operation = xmlmap.StringField(xpath="name(../../../..)")


class Keyword(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Keyword'

    keyword = xmlmap.StringField(xpath="*[local-name()='..']")


class ServiceMetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'structure.Organization'

    name = xmlmap.StringField(xpath="*[local-name()='ContactPersonPrimary']/*[local-name()='ContactOrganization']")
    person_name = xmlmap.StringField(xpath="*[local-name()='ContactPersonPrimary']/*[local-name()='ContactPerson']")
    phone = xmlmap.StringField(xpath="*[local-name()='ContactVoiceTelephone']")
    facsimile = xmlmap.StringField(xpath="*[local-name()='ContactFacsimileTelephone']")
    email = xmlmap.StringField(xpath="*[local-name()='ContactElectronicMailAddress']")
    country = xmlmap.StringField(xpath="*[local-name()='ContactAddress']/*[local-name()='Country']")
    postal_code = xmlmap.StringField(xpath="*[local-name()='ContactAddress']/*[local-name()='PostCode']")
    city = xmlmap.StringField(xpath="*[local-name()='ContactAddress']/*[local-name()='City']")
    state_or_province = xmlmap.StringField(xpath="*[local-name()='ContactAddress']/*[local-name()='StateOrProvince']")
    address = xmlmap.StringField(xpath="*[local-name()='ContactAddress']/*[local-name()='Address']")


class MimeType(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.MimeType'
    mime_type = xmlmap.StringField(xpath=".")


class Style(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Style'
    name = xmlmap.StringField(xpath="*[local-name()='Name']")
    title = xmlmap.StringField(xpath="*[local-name()='Title']")
    legend_uri = xmlmap.StringField(xpath="*[local-name()='LegendURL']/*[local-name()='OnlineResource']/@*[local-name()='href']")
    height = xmlmap.IntegerField(xpath="*[local-name()='LegendURL']/@*[local-name()='height']")
    width = xmlmap.IntegerField(xpath="*[local-name()='LegendURL']/@*[local-name()='width']")
    mime_type = xmlmap.NodeField(xpath="*[local-name()='LegendURL']/*[local-name()='Format']", node_class=MimeType)


class Layer(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Layer'

    children = xmlmap.NodeListField(xpath="*[local-name()='Layer']", node_class="self")

    identifier = xmlmap.StringField(xpath="*[local-name()='Name']")

    styles = xmlmap.NodeListField(xpath="*[local-name()='Style']", node_class=Style)

    scale_min = xmlmap.IntegerField(xpath="*[local-name()='ScaleHint']/@*[local-name()='min']")
    scale_max = xmlmap.IntegerField(xpath="*[local-name()='ScaleHint']/@*[local-name()='max']")

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

    # todo: SimpleBooleanField does not support multiple false values such as None and 0 for example
    is_queryable = xmlmap.SimpleBooleanField(xpath="@*[local-name()='queryable']", true=1, false=0)
    is_opaque = xmlmap.SimpleBooleanField(xpath="@*[local-name()='opaque']", true=1, false=0)
    is_cascaded = xmlmap.SimpleBooleanField(xpath="@*[local-name()='cascaded']", true=1, false=0)

    # todo: create LayerMetadata class
    # title = xmlmap.StringField(xpath="*[local-name()='Title']")
    # abstract = xmlmap.StringField(xpath="*[local-name()='Abstract']")


class ServiceMetadata(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Metadata'

    identifier = xmlmap.StringField(xpath="*[local-name()='Name']")
    title = xmlmap.StringField(xpath="*[local-name()='Title']")
    abstract = xmlmap.StringField(xpath="*[local-name()='Abstract']")
    fees = xmlmap.StringField(xpath="*[local-name()='Fees']")
    access_constraints = xmlmap.StringField(xpath="*[local-name()='AccessConstraints']")
    online_resource = xmlmap.StringField(xpath="*[local-name()='OnlineResource']/@*[local-name()='href']")

    keywords = xmlmap.NodeListField(xpath="*[local-name()='KeywordList']/*[local-name()='Keyword']", node_class=Keyword)
    contact = xmlmap.NodeField(xpath="*[local-name()='ContactInformation']", node_class=ServiceMetadataContact)


class Service(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'service.Service'

    metadata = xmlmap.NodeField(xpath="*[local-name()='Service']",
                                node_class=ServiceMetadata)
    layers = xmlmap.NodeField(xpath="*[local-name()='Capability']/*[local-name()='Layer']",
                              node_class=Layer)
    service_urls = xmlmap.NodeListField(xpath="*[local-name()='Capability']/*[local-name()='Request']//*[local-name()='DCPType']/*[local-name()='HTTP']//*[local-name()='OnlineResource']",
                                        node_class=ServiceUrl)


if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    xml_obj = xmlmap.load_xmlobject_from_file(filename=current_dir + '/dwd_wms_1.3.0.xml', xmlclass=Service)

    print(xml_obj.node)
