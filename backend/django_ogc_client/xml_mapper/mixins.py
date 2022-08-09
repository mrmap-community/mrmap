from django.conf import settings
from eulxml import xmlmap
from lxml.etree import XPathEvalError


class DBModelConverterMixin:
    """ Abstract class which implements some generic functions to get the db model class and all relevant field content
        as dict.
    """

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
                if not (isinstance(self._fields.get(key), xmlmap.NodeField) or
                        isinstance(self._fields.get(key), xmlmap.NodeListField)):
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
