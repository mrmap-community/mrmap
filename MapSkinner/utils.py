"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 17.04.19

"""
import urllib
import django_tables2
from django.http import HttpRequest
from MapSkinner.settings import THEME
from MapSkinner.themes import DARK_THEME, LIGHT_THEME
from MapSkinner.settings import PAGE_SIZE_OPTIONS, PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from django.utils.html import format_html


def execute_threads(thread_list):
    """ Executes a list of threads

    Args:
        thread_list (list): A list of threads
    Returns: nothing
    """
    for thread in thread_list:
        thread.start()
    for thread in thread_list:
        thread.join()


def resolve_none_string(val: str):
    """ To avoid 'none' or 'NONE' as strings, we need to resolve this to the NoneType

    Args:
        val(str): The potential none value as string
    Returns:
        None if the string is resolvable to None or the input parameter itself
    """
    val_u = val.upper()
    if val_u == "NONE":
        return None
    return val


def resolve_boolean_attribute_val(val):
    """ To avoid boolean values to be handled as strings, this function returns the boolean value of a string.

    If the provided parameter is not resolvable it will be returned as it was.

    Args:
        val:
    Returns:
         val
    """

    try:
        val = bool(int(val))
    except (TypeError, ValueError) as e:
        if isinstance(val, str):
            val_tmp = val.upper()
            if val_tmp == "FALSE":
                return False
            if val_tmp == "TRUE":
                return True
    return val


def set_uri_GET_param(uri: str, param: str, val):
    """ Changes a parameter in an uri to a given value.

    If the parameter does not exist, it will be added

    Args:
        uri (str): The uri
        param (str): The parameter that shall be changed
        val: The new value
    Returns:
        uri (str): The changed uri
    """
    val = str(val)
    base_uri = urllib.parse.urlsplit(uri)
    query_dict = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(uri).query))

    if "http" not in base_uri[0]:
        # the given 'uri' parameter is not a full uri, but rather the query part
        query_dict = dict(urllib.parse.parse_qsl(uri))
        if len(query_dict) == 0:
            raise ValueError("Uri parameter could not be resolved")

    changed = False

    for key, key_val in query_dict.items():
        if key.upper() == param.upper():
            query_dict[key] = val
            changed = True
            break

    if not changed:
        # the parameter didn't exist yet
        query_dict[param] = val

    query = urllib.parse.urlencode(query_dict, safe=", :")
    base_uri = base_uri._replace(query=query)
    uri = urllib.parse.urlunsplit(base_uri)

    return uri


def prepare_table_pagination_settings(request: HttpRequest, table: django_tables2, param_lead: str):
    return prepare_list_pagination_settings(request, list(table.rows), param_lead)


def prepare_list_pagination_settings(request: HttpRequest, l: list, param_lead: str):
    page_size_options = list(filter(lambda item: item <= len(l), PAGE_SIZE_OPTIONS))

    if not page_size_options.__contains__(len(l)):
        page_size_options.append(len(l))

    page_size_options = list(filter(lambda item: item <= PAGE_SIZE_MAX, page_size_options))

    pagination = {'page_size_param': param_lead + '-size',
                  'page_size_options': page_size_options,
                  'page_name': param_lead + '-page'
                  }

    if PAGE_SIZE_DEFAULT <= page_size_options[-1]:
        page_size = PAGE_SIZE_DEFAULT
    else:
        page_size = page_size_options[-1]

    pagination.update({'page_size': request.GET.get(pagination.get('page_size_param'), page_size)})

    return pagination


def get_theme():
    if THEME == 'DARK':
        return DARK_THEME
    else:
        return LIGHT_THEME


def get_ok_nok_icon(value):
    if value:
        return format_html("<i class='fas fa-check text-success'></i>")
    else:
        return format_html("<i class='fas fa-times text-danger'></i>")