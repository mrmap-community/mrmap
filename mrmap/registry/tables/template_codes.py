VALUE_TABLE_VIEW_LINK = """
{% load i18n %}
{% if value.get_table_url %}
<a href="{{value.get_table_url}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show table view' %}">{{value}}</a>
{% endif %}
"""
SERVICE_DETAIL_ICONS = """
{% load i18n %}
{% if record.get_tree_view_url %}
<a href="{{record.get_tree_view_url}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show tree view' %}">{{ICONS.HIERARCHY}}</a>
{% endif %}
{% if record.get_xml_view_url %}
<a href="{{record.get_xml_view_url}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show dataset metadata as xml representation' %}">{{ICONS.CAPABILITIES}}</a>
{% endif %}
"""
LAYER_FEATURE_TYPE_DETAIL_ICONS = """
{% load i18n %}
{% if record.service.get_tree_view_url %}
<a href="{{record.service.get_tree_view_url}}?collapse={{record.pk}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show tree view' %}">{{ICONS.HIERARCHY}}</a>
{% endif %}
{% if record.get_xml_view_url %}
<a href="{{record.get_xml_view_url}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show dataset metadata as xml representation' %}">{{ICONS.CAPABILITIES}}</a>
{% endif %}
"""
FEATURE_TYPE_ELEMENT_DETAIL_ICONS = """
{% load i18n %}
{% if record.feature_type.service.get_tree_view_url %}
<a href="{{record.feature_type.service.get_tree_view_url}}?collapse={{record.feature_type.pk}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show tree view' %}">{{ICONS.HIERARCHY}}</a>
{% endif %}
"""
METADATA_DETAIL_ICONS = """
{% load i18n %}
{% if record.get_xml_view_url %}
<a href="{{record.get_xml_view_url}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show dataset metadata as xml representation' %}">{{ICONS.CAPABILITIES}}</a>
{% endif %}
{% if record.get_absolute_url %}
<a href="{{record.get_absolute_url}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show dataset metadata as html representation' %}">{{ICONS.NEWSPAPER}}</a>
{% endif %}
"""
SERVICE_TABLE_ACTIONS = """
{% load i18n %}
{% load guardian_tags %}
{% load custom_template_filters %}
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
    {% if record|get_validate_url %}
    <a href="{{record|get_validate_url}}" class="btn btn-sm btn-primary mr-1" data-toggle="tooltip" data-placement="left" title="{% trans 'Validate' %}">{{ ICONS.VALIDATION|safe }}</a>
    {% endif %}
    {% if "change_service" in perms and record.get_activate_url%}
    <form class="mr-1" action="{{record.get_activate_url}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="is_active" {% if not record.is_active %}value="on"{% endif %}>
      <button type="submit" class="btn btn-sm {% if record.is_active %}btn-warning{% else %}btn-success{% endif %}" data-toggle="tooltip" data-placement="left" title="{% if record.is_active %}{% trans 'Deactivate the resource' %}{% else %}{% trans 'Activate the resource' %}{% endif %}">{{ ICONS.POWER_OFF|safe }}</button>
    </form>
    {% endif %}
    {% if "change_service" in perms and record.get_change_url%}
    <a class="btn btn-sm btn-warning mr-1" href="{{record.get_change_url}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Edit this service' %}">
      {{ ICONS.EDIT|safe }}
    </a>
    {% endif %}
    {% if "delete_service" in perms and record.get_delete_url %}
    <a class="btn btn-sm btn-danger" href="{{record.get_delete_url}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Remove this resource' %}">
      {{ ICONS.DELETE|safe }}
    </a>
    {% endif %}
</div>
"""
LAYER_TABLE_ACTIONS = """
{% load i18n %}
{% load guardian_tags %}
{% load custom_template_filters %}
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
    {% if record|get_validate_url %}
    <a href="{{record|get_validate_url}}" class="btn btn-sm btn-primary" data-toggle="tooltip" data-placement="left" title="{% trans 'Validate' %}">{{ ICONS.VALIDATION|safe }}</a>
    {% endif %}
    {% if "change_layer" in perms and record.get_change_url %}
    <form class="mr-1" action="{{record.get_change_url}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="is_active" {% if not record.is_active %}value="on"{% endif %}>
      <button type="submit" class="btn btn-sm {% if record.is_active %}btn-warning{% else %}btn-success{% endif %}" data-toggle="tooltip" data-placement="left" title="{% if record.is_active %}{% trans 'Deactivate the resource' %}{% else %}{% trans 'Activate the resource' %}{% endif %}">{{ ICONS.POWER_OFF|safe }}</button>
    </form>
    {% endif %}
</div>
"""
FEATURE_TYPE_TABLE_ACTIONS = """
{% load i18n %}
{% load guardian_tags %}
{% load custom_template_filters %}
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
    {% if record|get_validate_url %}
    <a href="{{record|get_validate_url}}" class="btn btn-sm btn-primary" data-toggle="tooltip" data-placement="left" title="{% trans 'Validate' %}">{{ ICONS.VALIDATION|safe }}</a>
    {% endif %}
    {% if "change_featuretype" in perms and record.get_change_url %}
    <form class="mr-1" action="{{record.get_change_url}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="is_active" {% if not record.is_active %}value="on"{% endif %}>
      <button type="submit" class="btn btn-sm {% if record.is_active %}btn-warning{% else %}btn-success{% endif %}" data-toggle="tooltip" data-placement="left" title="{% if record.is_active %}{% trans 'Deactivate the resource' %}{% else %}{% trans 'Activate the resource' %}{% endif %}">{{ ICONS.POWER_OFF|safe }}</button>
    </form>
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
