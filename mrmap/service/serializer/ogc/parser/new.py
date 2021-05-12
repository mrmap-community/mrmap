import os

from eulxml import xmlmap
from django.apps import apps
from django.db import models

GENERIC_NAMESPACE_TEMPLATE = "*[local-name()='{}']"


class DBModelConverterMixin:
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


class Keyword(xmlmap.XmlObject):
    keyword = xmlmap.StringField(xpath="*[local-name()='..']")


class ServiceMetadataContact(xmlmap.XmlObject):
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


class ServiceMetadata(xmlmap.XmlObject):
    name = xmlmap.StringField(xpath="*[local-name()='Name']")
    title = xmlmap.StringField(xpath="*[local-name()='Title']")
    abstract = xmlmap.StringField(xpath="*[local-name()='Abstract']")
    fees = xmlmap.StringField(xpath="*[local-name()='Fees']")
    access_constraints = xmlmap.StringField(xpath="*[local-name()='AccessConstraints']")
    online_resource = xmlmap.StringField(xpath="*[local-name()='OnlineResource']/@*[local-name()='href']")

    keywords = xmlmap.NodeListField(xpath="*[local-name()='KeywordList']/*[local-name()='Keyword']", node_class=Keyword)
    contact = xmlmap.NodeField(xpath="*[local-name()='ContactInformation']", node_class=ServiceMetadataContact)


class Service(xmlmap.XmlObject):
    service_metadata = xmlmap.NodeField(xpath="*[local-name()='Service']", node_class=ServiceMetadata)


if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    xml_obj = xmlmap.load_xmlobject_from_file(filename=current_dir + '/dwd_wms_1.3.0.xml', xmlclass=Service)

    print(xml_obj.node)
