from typing import Callable, Dict, Iterable, List
from urllib import parse

from extras.utils import camel_to_snake
from ows_lib.xml_mapper.mixins import CallbackList
from registry.xmlmapper.exceptions import SemanticError


class OperationUrl:
    """Helper class to flatten operationurl information which are stored in the xml path."""

    def __init__(self, method: str, operation: str, mime_types: List[str], url: str, callback: Callable = None) -> None:
        self.__method = method
        self.__operation = operation
        self.__mime_types = mime_types
        self.__url = url
        self._callback = callback

    def __str__(self) -> str:
        return f"op: {self.operation} | http method: {self.method} | url: {self.url}"

    @property
    def method(self) -> str:
        return self.__method

    @method.setter
    def method(self, value: str) -> None:
        """Custom setter to trigger callback function to update xml nodes"""
        self.__method = value
        if self._callback:
            self._callback(self)

    @property
    def operation(self) -> str:
        return self.__operation

    @operation.setter
    def operation(self, value: str) -> None:
        self.__operation = value
        if self._callback:
            self._callback(self)

    @property
    def url(self) -> str:
        return self.__url

    @url.setter
    def url(self, value: str) -> None:
        self.__url = value
        if self._callback:
            self._callback(self)

    @property
    def mime_types(self) -> List[str]:
        return self.__mime_types

    @mime_types.setter
    def mime_types(self, value: List[str]):
        self.__mime_types = value
        if self._callback:
            self._callback(self)

    def transform_to_model(self) -> Dict:
        attr = {}
        if self.operation:
            attr.update({"operation": self.operation})
        if self.url:
            attr.update({"url": self.url})
        if self.method:
            attr.update({"method": self.method})
        return attr


class ReferenceSystemMixin:

    _code = None
    _prefix = None

    def __str__(self) -> str:
        return self._ref_system

    @property
    def _ref_system(self):
        raise NotImplementedError

    def _extract_ref_system(self) -> None:
        if "::" in self._ref_system:
            # example: ref_system = urn:ogc:def:crs:EPSG::4326
            code = self._ref_system.rsplit(":")[-1]
            prefix = self._ref_system.rsplit(":")[-3]
        elif ":" in self._ref_system:
            # example: ref_system = EPSG:4326
            code = self._ref_system.rsplit(":")[-1]
            prefix = self._ref_system.rsplit(":")[-2]
        else:
            raise SemanticError("reference system unknown")

        self._code = code
        self._prefix = prefix

    @property
    def code(self) -> str:
        if not self._code:
            self._extract_ref_system()
        return self._code

    @code.setter
    def code(self, new_code) -> None:
        self._ref_system = f"{self._prefix}:{new_code}"

    @property
    def prefix(self) -> str:
        if not self._prefix:
            self._extract_ref_system()
        return self._prefix

    @prefix.setter
    def prefix(self, new_prefix) -> None:
        self._ref_system = f"{new_prefix}:{self._code}"

    def transform_to_model(self) -> Dict:
        attr = {}
        if self.prefix:
            attr.update({"prefix": self.prefix})
        if self.code:
            attr.update({"code": self.code})
        return attr


class OGCServiceTypeMixin:

    @property
    def _name(self):
        raise NotImplementedError

    @property
    def name(self) -> str:
        """ Custom property, cause the parsed name of the root element doesn't contains the right
            value for database. We need to parse again cause the root attribute contains different service type names
            as we store in our database.

            Returns:
                field_dict (dict): the dict which contains all needed information

            Raises:
                SemanticError if service name or version can not be found
        """
        if ":" in self._name:
            name = self._name.split(":", 1)[-1]
        elif " " in self._name:
            name = self._name.split(" ", 1)[-1]
        else:
            name = self._name

        name = name.lower()

        if name not in ["wms", "wfs", "csw"]:
            raise SemanticError(f"could not determine the service type for the parsed capabilities document. "
                                f"Parsed name was {name}")

        return name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value


class OGCServiceMixin:
    """Abstract class for all OGCService xml mappers,
    which implements functionality for global usage."""
    _operation_urls: CallbackList = []

    @property
    def _possible_operations(self):
        raise NotImplementedError

    @property
    def operation_urls(self) -> List[OperationUrl]:
        """Custom getter to merge all operation urls as plane OperationUrl object."""
        if not self._operation_urls:
            _operation_urls = []

            for possible_operation in self._possible_operations:
                mime_types_attr_name = f"_{camel_to_snake(possible_operation)}_mime_types"
                mime_types = getattr(self, mime_types_attr_name)

                get_url_attr_name = f"_{camel_to_snake(possible_operation)}_get_url"
                get_url = getattr(self, get_url_attr_name)

                post_url_attr_name = f"_{camel_to_snake(possible_operation)}_post_url"
                post_url = getattr(self, post_url_attr_name)

                if get_url:
                    _operation_urls.append(
                        OperationUrl(
                            method="Get",
                            operation=possible_operation,
                            mime_types=mime_types,
                            url=get_url,
                            callback=self._update_operation_url_xml_node)
                    )
                if post_url:
                    _operation_urls.append(
                        OperationUrl(
                            method="Post",
                            operation=possible_operation,
                            mime_types=mime_types,
                            url=post_url,
                            callback=self._update_operation_url_xml_node)
                    )

            self._operation_urls = CallbackList(
                _operation_urls, callback=self._handle_operation_urls_list_operation)

        return self._operation_urls

    @operation_urls.setter
    def operation_urls(self, operation_urls: List[OperationUrl]):
        self._clear_all_operation_urls()
        for operation_url in operation_urls:
            self._update_operation_url_xml_node_by_name(
                operation_url=operation_url)

    def _update_operation_url_xml_node_by_name(self, operation_url: OperationUrl, remove: bool = False):
        # find url attribute and update it
        url_attr_name = f"_{camel_to_snake(operation_url.operation)}_{operation_url.method.lower()}_url"
        setattr(self, url_attr_name, None if remove else operation_url.url)

        # find mime_types list attribute and update it
        mime_types_attr_name = f"_{camel_to_snake(operation_url.operation)}_mime_types"
        if remove and not self._operation_has_get_and_post(operation_url):
            setattr(self, mime_types_attr_name, [])
        elif not remove:
            mime_types = getattr(self, mime_types_attr_name)
            new_mime_types = filter(
                lambda mime_type: mime_type not in getattr(self, mime_types_attr_name), operation_url.mime_types)
            mime_types.extend(new_mime_types)

    def _update_operation_url_xml_node(self, operation_url: OperationUrl, remove: bool = False) -> None:
        if operation_url.operation in self._possible_operations:
            self._update_operation_url_xml_node_by_name(
                operation_url, remove)
            return
        raise ValueError(
            f"unsuported operation: {operation_url.operation}")

    def _handle_operation_urls_list_operation(self, list_operation, items: OperationUrl = None) -> None:
        """Custom setter to set/append new operation urls. The XML will be build implicitly by using this setter."""

        if isinstance(items, Iterable):
            for item in items:
                if not item._callback:
                    item._callback = self._update_operation_url_xml_node
        else:
            if items and not items._callback:
                items._callback = self._update_operation_url_xml_node

        match list_operation:
            case "append" | "insert":
                self._update_operation_url_xml_node(items)
            case "extend":
                [self._update_operation_url_xml_node(
                    item) for item in items]
            case "pop" | "remove":
                self._update_operation_url_xml_node(items, True)
            case "clear":
                self._clear_all_operation_urls()

    def _clear_all_operation_urls(self) -> None:
        for possible_operation in self._possible_operations:
            get_url_attr_name = f"_{camel_to_snake(possible_operation)}_get_url"
            setattr(self, get_url_attr_name, None)

            post_url_attr_name = f"_{camel_to_snake(possible_operation)}_post_url"
            setattr(self, post_url_attr_name, None)

            mime_types_attr_name = f"_{camel_to_snake(possible_operation)}_mime_types"
            setattr(self, mime_types_attr_name, [])
        self._operation_urls = []

    def _operation_has_get_and_post(self, operation_url: OperationUrl) -> bool:
        return self.get_operation_url_by_name_and_method(name=operation_url.operation, method="Get") and self.get_operation_url_by_name_and_method(name=operation_url.operation, method="Post")

    def get_operation_url_by_name_and_method(self, name, method) -> OperationUrl:
        return next((operation_url for operation_url in self.operation_urls if operation_url.operation == name and operation_url.method == method), None)

    def camouflage_urls(self, new_domain: str, scheme: str = None) -> None:
        for operation_url in self.operation_urls:
            parsed = parse.urlparse(operation_url.url)
            if scheme:
                replaced: parse.ParseResult = parsed._replace(
                    netloc=new_domain, scheme=scheme)
            else:
                replaced: parse.ParseResult = parsed._replace(
                    netloc=new_domain)
            operation_url.url = replaced.geturl()
