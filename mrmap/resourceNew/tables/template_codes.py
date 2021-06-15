SERVICE_DETAIL_ICONS = """
{% load i18n %}
{% if record.get_tree_view_url %}
<a href="{{record.get_tree_view_url}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show tree view' %}">{{ICONS.HIERARCHY}}</a>
{% endif %}
</div>
"""
LAYER_FEATURE_TYPE_DETAIL_ICONS = """
{% load i18n %}
{% if record.service.get_tree_view_url %}
<a href="{{record.service.get_tree_view_url}}?collapse={{record.pk}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show tree view' %}">{{ICONS.HIERARCHY}}</a>
{% endif %}
</div>
"""
FEATURE_TYPE_ELEMENT_DETAIL_ICONS = """
{% load i18n %}
{% if record.feature_type.service.get_tree_view_url %}
<a href="{{record.feature_type.service.get_tree_view_url}}?collapse={{record.feature_type.pk}}" data-toggle="tooltip" data-placement="left" title="{% trans 'Show tree view' %}">{{ICONS.HIERARCHY}}</a>
{% endif %}
</div>
"""
SERVICE_TABLE_ACTIONS = """
{% load i18n %}
{% load guardian_tags %}
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
    {% if "change_service" in perms and record.get_change_url%}
    <form class="mr-1" action="{{record.get_change_url}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="is_active" {% if not record.is_active %}value="on"{% endif %}>
      <button type="submit" class="btn btn-sm {% if record.is_active %}btn-warning{% else %}btn-success{% endif %}" data-toggle="tooltip" data-placement="left" title="{% if record.is_active %}{% trans 'Deactivate the resource' %}{% else %}{% trans 'Activate the resource' %}{% endif %}">{{ ICONS.POWER_OFF|safe }}</button>
    </form>
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
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
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
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
    {% if "change_featuretype" in perms and record.get_change_url %}
    <form class="mr-1" action="{{record.get_change_url}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="is_active" {% if not record.is_active %}value="on"{% endif %}>
      <button type="submit" class="btn btn-sm {% if record.is_active %}btn-warning{% else %}btn-success{% endif %}" data-toggle="tooltip" data-placement="left" title="{% if record.is_active %}{% trans 'Deactivate the resource' %}{% else %}{% trans 'Activate the resource' %}{% endif %}">{{ ICONS.POWER_OFF|safe }}</button>
    </form>
    {% endif %}
</div>
"""

