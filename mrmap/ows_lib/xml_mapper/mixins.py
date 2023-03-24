from typing import Callable, Dict

from django.conf import settings
from eulxml import xmlmap
from eulxml.xmlmap import XmlObject
from lxml.etree import XPathEvalError


class CallbackList(list):

    def __init__(self, iterable, callback: Callable, *args, **kwargs) -> None:
        super().__init__(iterable, *args, **kwargs)
        self.callback = callback

    def append(self, item) -> None:
        super().append(item)
        self.callback(list_operation="append", items=item)

    def extend(self, items) -> None:
        super().extend(items)
        self.callback(list_operation="extend", items=items)

    def pop(self, __index):
        operation_url_to_pop = self[__index]
        super().pop(__index)
        self.callback(list_operation="pop", items=operation_url_to_pop)

    def clear(self) -> None:
        super().clear()
        self.callback(list_operation="clear")

    def insert(self, __index, __object) -> None:
        super().insert(__index, __object)
        self.callback(list_operation="insert", items=__object)

    def remove(self, __value) -> None:
        super().remove(__value)
        self.callback(list_operation="remove", items=__value)


class CustomXmlObject(XmlObject):
    """ Custom Xml Object class which implements some generic functions to get the db model class and all relevant field content
        as dict.
    """

    def __get_xml_mapper_fields(self) -> Dict:
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
                    _something = xmlmap.StringField('something')

                The SomeXmlObject().get_field_dict() function return {'name': 'Something'}

        Returns:
            field_dict (dict): the dict which contains all simple fields of the object it self.

        """
        field_dict = {}

        for key in filter(lambda key: not key.startswith('_'), self._fields.keys()):
            try:
                if not (isinstance(self._fields.get(key), xmlmap.NodeField) or
                        isinstance(self._fields.get(key), xmlmap.NodeListField) or
                        isinstance(self._fields.get(key), xmlmap.StringListField)):
                    if isinstance(self._fields.get(key), xmlmap.SimpleBooleanField) and getattr(self, key) is None or \
                       isinstance(self._fields.get(key), xmlmap.StringField) and getattr(self, key) is None or \
                       isinstance(self._fields.get(key), xmlmap.IntegerField) and getattr(self, key) is None:
                        # we don't append None values, cause if we construct a model with key=None and the db field
                        # don't allow Null values but has a default for Boolean the db will raise integrity
                        # errors.
                        continue
                    field_dict.update({key: getattr(self, key)})
            except XPathEvalError as e:
                settings.ROOT_LOGGER.error(
                    msg=f"error during parsing field: {key} in class {self.__class__.__name__}")
                settings.ROOT_LOGGER.exception(
                    e, stack_info=True, exc_info=True)
        return field_dict

    def transform_to_model(self) -> Dict:
        """
        Returns a dict of public objects fields and there values
        """
        field_dict = self.__get_xml_mapper_fields()
        for key, value in self.__dict__.items():
            if key.startswith('_') or key[0].isupper() or key != 'context' or value is None or key in self._fields.keys():
                break
            field_dict.update({key: value})
        return field_dict
