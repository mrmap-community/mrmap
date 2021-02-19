"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 23.04.20

"""
import json
import random
import string
from django.core.exceptions import FieldError
from django.db.models import QuerySet
from django.test import RequestFactory, Client
from django.urls import reverse
from django_filters import FilterSet
from django_tables2 import RequestConfig

from MrMap import utils
from MrMap.tables import MrMapTable
from structure.models import MrMapUser


def activate_service(self, is_active: bool):
    """ Toggles the activity status of a service and it's metadata

    Args:
        is_active (bool): Whether the service shall be activated or not
    Returns:
         nothing
    """
    self.is_active = is_active
    self.metadata.is_active = is_active

    linked_mds = self.metadata.related_metadata.all()
    for md_relation in linked_mds:
        md_relation.metadata_to.is_active = is_active
        md_relation.metadata_to.save(update_last_modified=False)

    self.metadata.save(update_last_modified=False)
    self.save(update_last_modified=False)


def generate_random_string(len: int):
    """ Creates a randomly generated string of uppercase letters

    Args:
        len (int): The desired length
    Returns:
         random_string (str)
    """
    return ''.join(random.choices(string.ascii_uppercase, k=len))


def check_table_sorting(table: MrMapTable, url_path_name: str, sorting_parameter: str):
    """ Checks the sorting of a MrMapTable object.

    This function returns two elements, so call it like
    ```
    sorting_failed, sorting_results = check_table_sorting(...)
    ```

    Args:
        table (MrMapTable): An instance of a MrMapTable (or inherited)
        url_path_name (str): Identifies the url path name like `structure:groups-index` where the table would be rendered
        sorting_parameter (str): Identifies the GET parameter name, that holds the ordering column name
    Returns:
        sorting_implementation_failed (dict): Contains results if the sorting created an exception
                                              (maybe due to a custom sorting functionality)
        sorting_results (dict): Contains results if the sorting was properly done or not
    """
    request_factory = RequestFactory()
    sorting_implementation_failed = {}
    sorting_results = {}
    sort_ways = ["", "-"]

    for sorting in sort_ways:
        for column in table.columns:
            request = request_factory.get(
                reverse(url_path_name) + '?{}={}{}'.format(
                    sorting_parameter,
                    sorting,
                    column.name
                )
            )

            RequestConfig(request).configure(table)

            try:
                if "actions" in column.accessor:
                    break
                # Check if correctly sorted
                post_sorting = [utils.get_nested_attribute(row.record, column.accessor).__str__() for row in table.rows]
                try:
                    # For numerical sorting, the strings have to be casted to Integer - if possible
                    post_sorting = [int(p) for p in post_sorting]
                except ValueError:
                    pass
                python_sorted = sorted(post_sorting, reverse=sorting == "-")

                sorting_result = post_sorting == python_sorted
                sorting_results[column] = sorting_result
                sorting_implementation_failed[column.name] = False
            except FieldError:
                sorting_implementation_failed[column.name] = True

    return sorting_implementation_failed, sorting_results


def check_table_filtering(table: MrMapTable, filter_parameter: str, filter_class, queryset: QuerySet,
                          table_class, user: MrMapUser):
    """ Checks if the filter functionality of a MrMapTable is working

    Args:
        table (MrMapTable): An instance of a MrMapTable (or inherited)
        filter_parameter (str): Identifies the parameter used for filtering in the table (e.g. 'gsearch' in Groups)
        filter_class: The class used for creating the table filter (e.g. GroupFilter)
        queryset (QuerySet): The queryset containing the data which is displayed in the table
        table_class: The class used for creating the table itself (e.g. GroupTable)
        user (MrMapUser): The performing user object
    Returns:
        filtering_results (dict): Contains key-value pairs like (filtered_for_string: True|False)
    """
    filtering_results = {}

    # Filter each row for each value in each column and check if only matching elements stay there
    for row in table.rows:
        for col in table.columns:
            if "actions" in col.accessor:
                break
            filter_for = utils.get_nested_attribute(row.record, col.accessor).__str__()

            # Generic approach to filter on various types of tables
            table_filter = filter_class({filter_parameter: filter_for}, queryset)

            request_factory = RequestFactory()
            # Create an instance of a GET request.
            request = request_factory.get('/')
            # Recall that middleware are not supported. You can simulate a
            # logged-in user by setting request.user manually.
            request.user = user
            filtered_table = table_class(data=table_filter.qs, request=request)

            # Iterate over each row in the filtered table and check if all values inside the current column are valid
            for tmp_row in filtered_table.rows:
                col_val = utils.get_nested_attribute(tmp_row.record, col.accessor).__str__()
                filtering_results[filter_for] = filter_for in col_val.__str__()

    return filtering_results


def check_filtering(filter_class: FilterSet, filter_param: str, filter_attribute_name: str, queryset: QuerySet):
    """ Checks if a given FilterSet implementation works fine.

    Args:
        filter_class (FilterSet): An implemented class, inheriting from FilterSet (e.g. GroupFilter)
        filter_param (str): Identifier for the parameter (e.g. "gsearch")
        filter_attribute_name (str): Identifier for the attribute of an element, which is used for filtering (e.g. "name" of MrMapGroup model)
        queryset (QuerySet): A queryset containing test data
    Returns:
         filtering_successfull (bool)
    """
    cached_elements = list(queryset)
    filtering_successfull = True
    for elem in cached_elements:
        filter_for = utils.get_nested_attribute(elem, filter_attribute_name)
        filtered_queryset = filter_class(
            {
                filter_param: filter_for
            },
            queryset
        ).qs
        for filtered_elem in filtered_queryset:
            if filter_for not in utils.get_nested_attribute(filtered_elem, filter_attribute_name):
                filtering_successfull = False
                break
    return filtering_successfull


def check_autocompletion_response(elements_list: list, attrib_name: str, client: Client, url_path_name: str):
    """ Checks autocompletion of editor app

    Args:
        elements_list (list|QuerySet): List or QuerySet, containing all elements
        attrib_name (str): Name of the attribute that is used for autocompletion
        client (Client): A logged in client object
        url_path_name (str): The name of the url from urls.py
    Returns:
         ret_val (list): A list of return values, each a dict like {"val": bool, "elem": str}
    """
    ret_val = []
    for element in elements_list:
        response = client.get(
            reverse(url_path_name),
            {
                "q": utils.get_nested_attribute(element, attrib_name),
            }
        )
        found_elements = json.loads(response.content)["results"]
        elem_attr = utils.get_nested_attribute(element, attrib_name)
        for found_element in found_elements:
            found = elem_attr in found_element["text"]
            ret_val.append({
                "val": found,
                "elem": elem_attr
            })
    return ret_val