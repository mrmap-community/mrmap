"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 23.04.20

"""
from django.core.exceptions import FieldError
from django.test import RequestFactory
from django.urls import reverse
from django_tables2 import RequestConfig

from MapSkinner import utils
from MapSkinner.tables import MapSkinnerTable


def check_table_sorting(table: MapSkinnerTable, url_path_name: str, sorting_parameter: str):
    """ Checks the sorting of a MapSkinnerTable object.

    This function returns two elements, so call it like
    ```
    sorting_failed, sorting_results = _check_table_sorting(...)
    ```

    Args:
        table (MapSkinnerTable): An instance of a MapSkinnerTable (or inherited)
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
                # Check if correctly sorted
                post_sorting = [utils.get_nested_attribute(row.record, column.accessor).__str__() for row in table.rows]
                python_sorted = sorted(post_sorting, reverse=sorting == "-")

                sorting_result = post_sorting == python_sorted
                sorting_results[column] = sorting_result
                sorting_implementation_failed[column.name] = False
            except FieldError:
                sorting_implementation_failed[column.name] = True

    return sorting_implementation_failed, sorting_results
