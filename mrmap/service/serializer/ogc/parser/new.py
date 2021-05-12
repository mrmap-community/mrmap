import os

from eulxml import xmlmap
from django.apps import apps
from django.db import models

class OGCWebMapServiceMetadata(xmlmap.XmlObject):
    name = xmlmap.StringField(xpath='Name')
    title = xmlmap.StringField(xpath='Title')
    abstract = xmlmap.StringField(xpath='Abstract')
    fees = xmlmap.StringField(xpath='Fees')
    access_constraints = xmlmap.StringField(xpath='AccessConstraints')

    #keywords = xmlmap.StringListField('KeywordList/Keyword')
    class Meta:
        model = 'service.Metadata'

    def _get_model_class(self):
        if isinstance(self.model, str):
            app_label, model_name = self._meta.model.split('.', 1)
            return apps.get_model(app_label=app_label, model_name=model_name)
        elif issubclass(self.model, models.Model):
            return self._meta.model

    def to_db_model(self):
        return self._get_model_class(**self.__dict__)


class Service(xmlmap.XmlObject):
    service_metadata = xmlmap.NodeField(xpath='Service', node_class=OGCWebMapServiceMetadata)


if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    xml_obj = xmlmap.load_xmlobject_from_file(filename=current_dir + '/dwd_wms_1.3.0.xml', xmlclass=Service)

    print(xml_obj.node)
