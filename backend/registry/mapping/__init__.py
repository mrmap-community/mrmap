from django.db.models import Model
from odin import registration
from odin.mapping import FieldResolverBase
from odin.utils import getmeta
from ows_lib.xml_mapper.mixins import CustomXmlObject


class ModelFieldResolver(FieldResolverBase):
    """
    Field resolver for Django Models
    """

    def get_field_dict(self):
        meta = getmeta(self.obj)
        return {f.attname: f for f in meta.fields}


class XmlMapperFieldResolver(FieldResolverBase):
    """
    Field resolver for XML Objects
    """

    def get_field_dict(self):
        xml_obj = self.obj
        return {key: getattr(xml_obj, key) for key in filter(lambda key: not key.startswith('_'), xml_obj._fields.keys())}


registration.register_field_resolver(ModelFieldResolver, Model)
registration.register_field_resolver(XmlMapperFieldResolver, CustomXmlObject)
