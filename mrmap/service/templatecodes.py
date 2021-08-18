SERVICE_TABLE_ACTIONS = """
{% load i18n %}
{% load guardian_tags %}
{% load custom_template_filters %}
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
    {% if record|get_validate_url %}
    <a href="{{record|get_validate_url}}" class="btn btn-sm btn-primary" data-toggle="tooltip" data-placement="left" title="{% trans 'Validate' %}">{{ ICONS.VALIDATION|safe }}</a>
    {% endif %}
    {% if "change_service" in perms and record.get_activate_url %}
    <form class="mr-1" action="{{record.get_activate_url}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="is_active" {% if not record.is_active %}value="on"{% endif %}>
      <button type="submit" class="btn btn-sm {% if record.is_active %}btn-warning{% else %}btn-success{% endif %}" data-toggle="tooltip" data-placement="left" title="{% if record.is_active %}{% trans 'Deactivate the resource' %}{% else %}{% trans 'Activate the resource' %}{% endif %}">{{ ICONS.POWER_OFF|safe }}</button>
    </form>
    {% endif %}
    {% if "change_service" in perms and record.get_change_url%}
    <a class="btn btn-sm btn-warning mr-1" href="{{record.get_change_url}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Edit service' %}">
      {{ ICONS.EDIT|safe }}
    </a>
    {% endif %} 
    {% if record.get_harvest_url %}
    <form class="mr-1" action="{{record.get_harvest_url}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="service" value="{{record.pk}}">
      <button type="submit" class="btn btn-sm btn-info" data-toggle="tooltip" data-placement="left" title="{% trans 'Start harvesting process' %}">{{ ICONS.HARVEST|safe }}</button>
    </form>
    {% endif %}
    {% if "delete_service" in perms and record.get_delete_url %}
    <a class="btn btn-sm btn-danger" href="{{record.get_delete_url}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Remove this resource' %}">
      {{ ICONS.DELETE|safe }}
    </a>
    {% endif %}       
</div>
"""

MAP_CONTEXT_TABLE_ACTIONS = """
{% load i18n %}
<div class="d-inline-flex">
    <a class="btn btn-sm btn-warning mr-1" href="{{record.edit_view_uri}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Edit the map context' %}">
      {{ ICONS.EDIT|safe }}
    </a>
    <a class="btn btn-sm btn-danger" href="{{record.remove_view_uri}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Remove this map context' %}">
      {{ ICONS.DELETE|safe }}
    </a>
</div>
"""
