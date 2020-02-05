from django import template
register = template.Library()


@register.filter
def get_order_by_alias_from_request(request, order_by_alias):
    return request.get(order_by_alias,)


