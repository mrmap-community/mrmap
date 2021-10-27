PUBLISHES_REQUEST_BUTTON = """
{% load static i18n %}
{% load guardian_tags %}
{% get_obj_perms request.user for record as "obj_perms" %}

{% if record.get_change_url and "change_pendingrequest" in perms %}
<div class="d-inline-flex">
    <form class="mr-1" action="{{record.get_change_url}}" method="post">
        {% csrf_token %}
        <input type="hidden"  name="is_accepted" value="on">
        <button type="submit" class="btn btn-sm btn-success" data-toggle="tooltip" data-placement="top" title="{% trans 'Accept request' %}">{{{{ ICONS.OK|safe }}}}</button>
    </form>
    <form action="{{record.get_change_url}}" method="post">
        {% csrf_token %}
        <input type="hidden"  name="is_accepted" value="off">
        <button type="submit" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="top" title="{% trans 'Deny request' %}">{{{{ ICONS.NOK|safe }}}}</button>
    </form>
</div>
{% endif %}
"""


REMOVE_PUBLISHER_BUTTON = """
{% load static i18n %}
{% load guardian_tags %}
{% get_obj_perms request.user for record as "perms" %}
{% if record.get_change_url and "users.change_organization" in perms %}
<a class="btn btn-sm btn-danger" href="{{record.get_change_url}}" data-toggle="tooltip" data-placement="top" title="{% trans 'remove publisher' %}">{{{{ ICONS.DELETE|safe }}}}</a>
{% endif %}
"""
