from collections.abc import Iterable
from typing import Callable, Iterable, List
from urllib import parse

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
    _operation_urls: CallbackList = None

    def _update_or_create_operation_url_xml_node(self, operation_url: OperationUrl) -> None:
        match operation_url.operation:
            case "GetCapabilities":
                new_mime_types = filter(
                    lambda mime_type: mime_type not in self._get_capabilitites_mime_types, operation_url.mime_types)
                self._get_capabilitites_mime_types.extend(new_mime_types)
                if operation_url.method == "Get":
                    self._get_capabilitites_get_url = operation_url.url
                elif operation_url.method == "Post":
                    self._get_capabilitites_post_url = operation_url.url
            case _:
                raise ValueError(
                    f"unsuported operation: {operation_url.operation}")

    def _remove_operation_url_xml_node(self, operation_url: OperationUrl) -> None:
        match operation_url.operation:
            case "GetCapabilities":
                if operation_url.method == "Get":
                    self._get_capabilitites_get_url = None
                elif operation_url.method == "Post":
                    self._get_capabilitites_post_url = None
                if not self._operation_has_get_and_post(operation_url):
                    self._get_capabilitites_mime_types = []
            case _:
                raise ValueError(
                    f"unsuported operation: {operation_url.operation}")

    def _handle_operation_urls_list_operation(self, list_operation, items: OperationUrl = None) -> None:
        """Custom setter to set/append new operation urls. The XML will be build implicitly by using this setter."""

        if isinstance(items, Iterable):
            for item in items:
                if not item._callback:
                    item._callback = self._update_or_create_operation_url_xml_node
        else:
            if items and not items._callback:
                items._callback = self._update_or_create_operation_url_xml_node

        match list_operation:
            case "append" | "insert":
                self._update_or_create_operation_url_xml_node(items)
            case "extend":
                [self._update_or_create_operation_url_xml_node(
                    item) for item in items]
            case "pop" | "remove":
                self._remove_operation_url_xml_node(items)
            case "clear":
                self._clear_all_operation_urls()

    def _clear_all_operation_urls(self) -> None:
        self._get_capabilitites_mime_types = []
        self._get_capabilitites_get_url = None
        self._get_capabilitites_post_url = None

    def _operation_has_get_and_post(self, operation_url: OperationUrl) -> bool:
        return self.get_operation_url_by_name_and_method(name=operation_url.operation, method="Get") and self.get_operation_url_by_name_and_method(name=operation_url.operation, method="Post")

    @property
    def _get_capabilities_operation_urls(self) -> List[OperationUrl]:
        _operation_urls: List[OperationUrl] = []
        if self._get_capabilitites_get_url:
            _operation_urls.append(
                OperationUrl(
                    method="Get",
                    operation="GetCapabilities",
                    mime_types=self._get_capabilitites_mime_types,
                    url=self._get_capabilitites_get_url,
                    callback=self._update_or_create_operation_url_xml_node)
            )
        if self._get_capabilitites_post_url:
            _operation_urls.append(
                OperationUrl(
                    method="Post",
                    operation="GetCapabilities",
                    mime_types=self._get_capabilitites_mime_types,
                    url=self._get_capabilitites_post_url,
                    callback=self._update_or_create_operation_url_xml_node)
            )
        return _operation_urls

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
