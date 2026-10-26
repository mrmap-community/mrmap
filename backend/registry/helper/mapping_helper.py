"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 27.10.20

"""


def map_parameters(obj, parameter_map: dict):
    return {key: map_parameter(obj, value) for key, value in
            parameter_map.items()}


def map_parameter(obj, target_value):
    if isinstance(target_value, str):
        return map_string(obj, target_value)
    if isinstance(target_value, dict):
        return map_parameters(obj, target_value)
    elif isinstance(target_value, list):
        return [map_parameter(obj, v) for v in target_value]
    else:
        return target_value


def map_string(obj, target_value: str):
    if target_value.startswith('__'):
        property_name = target_value[2:]
        val = find(obj, property_name)
        return val
    return target_value


def find(obj, path: str):
    steps = path.split('.')
    for prop in steps:
        obj = obj[prop]
    return obj
