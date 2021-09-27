from importlib import import_module

from django import template

from extras.utils import camel_to_snake as util_camel_to_snake
from registry.models import ConformityCheckRun

register = template.Library()


@register.filter
def model_to_title(value):
    instance = value
    if hasattr(instance, 'icon'):
        return instance.icon + ' ' + instance._meta.verbose_name.__str__().title()
    else:
        return instance._meta.verbose_name.__str__().title()


@register.filter
def to_class_name(value):
    return value.__class__.__name__


@register.filter
def lower(value):
    return value.lower()


@register.filter
def camel_to_snake(value):
    return util_camel_to_snake(value)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_order_by_alias_from_request(request, order_by_alias):
    return request.get(order_by_alias, )


@register.filter
def isinst(value, class_str):
    split = class_str.split('.')
    return isinstance(value, getattr(import_module('.'.join(split[:-1])), split[-1]))


@register.filter
def duration_to_ms(duration):
    seconds = duration.total_seconds()
    milliseconds = seconds * 1000
    return milliseconds


@register.filter
def get_validate_url(item):
    return ConformityCheckRun.get_validate_url(item)
