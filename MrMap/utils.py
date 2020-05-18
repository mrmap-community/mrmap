"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 17.04.19

"""
import urllib
from MrMap.themes import DARK_THEME, LIGHT_THEME
from django.utils.html import format_html

from structure.models import MrMapUser
from MrMap.settings import DEBUG


def print_debug_mode(string: str):
    """ Only prints the string if the project runs in DEBUG mode (e.g. for development)

    Args:
        string (str): The string which shall be printed
    Returns:

    """
    if DEBUG:
        print(string)


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


def get_theme(user: MrMapUser):
    if user is None or user.theme is None:
        return LIGHT_THEME
    elif user.theme.name == 'DARK':
        return DARK_THEME
    else:
        return LIGHT_THEME


def get_default_theme():
    return LIGHT_THEME


def get_ok_nok_icon(value):
    if value:
        return format_html("<i class='fas fa-check text-success'></i>")
    else:
        return format_html("<i class='fas fa-times text-danger'></i>")


def get_nested_attribute(obj, attrib_str: str):
    """ Iterates over nested attributes of an object and returns the found attribute.

    Supports '.' based nested attribute notation, e.g. 'object.nested_1.nested_2'

    Args:
        obj: The object
        attrib_str (str): The nested attribute string
    Returns:
         val: The found attribute
    """
    attrs = attrib_str.split(".")
    val = obj
    for attr in attrs:
        val = val.__getattribute__(attr)

    return val

