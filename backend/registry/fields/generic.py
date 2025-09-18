from django_xml.models.fields import IntegerField, StringField
from registry.fields.maps import XPATH_MAP


class OWSFieldMixin:
    def __init__(self, field_name, *args, **kwargs):
        self.field_name = field_name
        super().__init__(*args, **kwargs)

    def get_xpath(self, instance):
        key = (instance.service_type, instance.version)
        if key not in XPATH_MAP:
            raise ValueError(f"Kein XPath-Mapping für {key} definiert")
        mapping = XPATH_MAP[key]
        if self.field_name not in mapping:
            raise ValueError(
                f"Feld '{self.field_name}' nicht im Mapping für {key} gefunden")
        return mapping[self.field_name]

    def __get__(self, instance, owner):
        if instance is None:
            return self
        xpath = self.get_xpath(instance)
        values = instance.xml.xpath(xpath)
        return values[0] if values else None

    def __set__(self, instance, value):
        xpath = self.get_xpath(instance)
        instance.xml.set(xpath, value)


class OWSStringField(OWSFieldMixin, StringField):
    pass


class OWSIntegerField(OWSFieldMixin, IntegerField):
    pass
