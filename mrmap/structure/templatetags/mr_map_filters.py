from importlib import import_module

from django import template
from django_bootstrap_swt.components import BootstrapComponent
from django_bootstrap_swt.utils import RenderHelper

register = template.Library()


@register.filter
def get_order_by_alias_from_request(request, order_by_alias):
    return request.get(order_by_alias,)


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
def render_item(item: BootstrapComponent):
    return item.render(safe=True)


