import typing
import warnings
from datetime import datetime
from inspect import signature
from typing import Dict, List, Tuple

from django.conf import settings
from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from drf_spectacular.openapi import AutoSchema
from extras.utils import deep_update
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import APIException
from rest_framework.fields import empty
from rest_framework.schemas.utils import is_list_view
from rest_framework.serializers import Serializer
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api import serializers, views
from rest_framework_json_api.utils import (format_field_name,
                                           get_related_resource_type,
                                           get_resource_name,
                                           get_resource_type_from_serializer)


class JsonApiAutoSchema(AutoSchema):
    """
    Extend DRF's openapi.AutoSchema for JSON:API serialization.
    """

    def get_serializer(self, path, method) -> Serializer | None:
        view = self.view

        if not hasattr(view, 'get_serializer'):
            return None

        try:
            return view.get_serializer()
        except APIException:
            warnings.warn('{}.get_serializer() raised an exception during '
                          'schema generation. Serializer fields will not be '
                          'generated for {} {}.'
                          .format(view.__class__.__name__, method, path))
            return None

    def _get_serializer_field(self, name: str) -> Dict | None:
        """Retuns serializer field object by the name of the field"""
        serializer = self.get_serializer(path=self.path, method=self.method)
        return serializer.fields.get(name, None)

    def _get_filter_parameters(self) -> Dict:
        """ JSON:API specific handling for sort parameter

        See also json:api docs: https://jsonapi.org/format/#fetching-sorting
        """
        parameters = super()._get_filter_parameters()
        sort_param = next(
            (parameter for parameter in parameters if parameter["name"] == "sort"), None)
        if sort_param and hasattr(self.view, "ordering_fields") and self.view.ordering_fields:
            self._patch_sort_param_schema(sort_param=sort_param)
        elif sort_param:
            # if sorting is not supported by the view, which is identified by the existing of the `ordering_fields` attribute,
            # then the json:api MUST retun 400 Bad Request.

            # So for that case, sorting is not supported for this endpoint. We need to drop the sort filter parameter.
            parameters.pop(parameters.index(sort_param))

        self._patch_translations_for_fields(parameters=parameters)

        return parameters

    def get_label_for_filter(self, filter_obj):
        # explcit title defined by user
        # cast to string to ensure django gettext_lazy is rendered correctly
        return str(filter_obj.label) if filter_obj.label else None

    def get_help_text_for_filter(self, filter_obj):
        # explicit help_text defined by user
        # cast to string to ensure django gettext_lazy is rendered correctly
        return str(filter_obj.help_text) if hasattr(filter_obj, "help_text") and filter_obj.help_text else None

    def get_title_and_description_for_filter_parameter(self, field_name) -> Tuple[str, str]:
        title = None
        description = None
        if hasattr(self.view, "filterset_class"):
            # only in case of filterset classes there is a possibility,
            # that the user set the label or title expliciet to describe what this filter does.
            _filter = self.view.filterset_class.declared_filters.get(
                field_name, None)
            if _filter:
                # only lookup into user specified filters,
                # cause otherwise the title and label are made from the django model stack.
                title = self.get_label_for_filter(filter_obj=_filter)
                description = self.get_help_text_for_filter(
                    filter_obj=_filter)

        return title, description

    def _get_field_name_from_filter_parameter_name(self, parameter_name):
        field_name = parameter_name.split("[")[1].split("]")[0]
        if "_" in field_name:
            field_name = field_name.split("_")[0]
        if "." in field_name:
            field_name = field_name.split(".")[0]
        return field_name

    def _patch_translations_for_fields(self, parameters: Dict):
        """Patching all parameter descriptions with the django translations"""
        for parameter in parameters:
            if "filter[" in parameter.get("name", ""):
                field_name = self._get_field_name_from_filter_parameter_name(
                    parameter_name=parameter["name"])
                title, description = self.get_title_and_description_for_filter_parameter(
                    field_name=field_name)
                if title:
                    parameter["title"] = title
                if description:
                    parameter["description"] = description

    def _patch_sort_param_schema(self, sort_param: Dict) -> None:
        """Patching all possible sortable columns as schema definition."""
        serializer = self.get_serializer(self.path, self.method)
        enum = []
        if isinstance(self.view.ordering_fields, str) and self.view.ordering_fields == "__all__":
            # All fields can be used to sort
            for field in serializer.fields.values():

                enum.append(
                    format_field_name(field.field_name))
        elif isinstance(self.view.ordering_fields, list):
            # only a subset of fields are provided as sortable
            for field_name in self.view.ordering_fields:
                enum.append(format_field_name(field_name))
        if enum:
            sort_param["schema"]["uniqueItems"] = True
            sort_param["schema"]["enum"] = enum

    def get_tags(self) -> List[str]:
        # TODO: add a setting wich allows to configure the behaviour
        return [get_resource_name(context={"view": self.view})]
