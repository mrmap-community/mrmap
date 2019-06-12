"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 17.04.19

"""
import hashlib


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


def sha256(_input: str):
    m = hashlib.sha256()
    m.update(_input.encode("UTF-8"))
    return m.hexdigest()


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
