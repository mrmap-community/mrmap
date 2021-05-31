from django.apps import apps
from django.db import models
from django.core.exceptions import ImproperlyConfigured
from eulxml import xmlmap
from lxml.etree import XPathEvalError
from service.settings import service_logger


class DBModelConverterMixin:
    """ Abstract class which implements some generic functions to get the db model class and all relevant field content
        as dict.
    """
    model = None

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
            try:
                if not isinstance(self._fields.get(key), xmlmap.NodeField) and \
                        not isinstance(self._fields.get(key), xmlmap.NodeListField):
                    if (isinstance(self._fields.get(key), xmlmap.SimpleBooleanField) or
                        isinstance(self._fields.get(key), xmlmap.StringField) or
                        isinstance(self._fields.get(key), xmlmap.DateTimeField)) \
                            and getattr(self, key) is None:
                        # we don't append None values, cause if we construct a model with key=None and the db field
                        # don't allow Null values but has a default for Boolean or string the db will raise integrity
                        # errors.
                        continue
                    field_dict.update({key: getattr(self, key)})
            except XPathEvalError as e:
                service_logger.error(msg=f"error during parsing field: {key} in class {self.__class__.__name__}")
                service_logger.exception(e, stack_info=True, exc_info=True)
        return field_dict
