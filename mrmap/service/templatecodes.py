RESOURCE_TABLE_ACTIONS = """
{% load i18n %}
{% load guardian_tags %}
{% get_obj_perms request.user for record as "perms" %}
<div class="d-inline-flex">
    {% if "activate_resource" in perms %}
    <form class="mr-1" action="{{record.activate_view_uri}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="is_active" {% if not record.is_active %}value="on"{% endif %}>
      <button type="submit" class="btn btn-sm {% if record.is_active %}btn-warning{% else %}btn-success{% endif %}" data-toggle="tooltip" data-placement="left" title="{% if record.is_active %}{% trans 'Deactivate the resource' %}{% else %}{% trans 'Activate the resource' %}{% endif %}">{{ ICONS.POWER_OFF|safe }}</button>
    </form>
    {% endif %}
    {% if record.service_type.value == 'csw' and "harvest_resource" in perms %}
    <form class="mr-1" action="{{record.harvest_view_uri}}" method="post">
      {% csrf_token %}
      <input type="hidden"  name="metadata" value="{{ record.pk }}">
      <button type="submit" class="btn btn-sm btn-info" data-toggle="tooltip" data-placement="left" title="{% trans 'Harvest the resource' %}">{{ ICONS.HARVEST|safe }}</button>
    </form>
    {% else %}
        {% if "change_metadata" in perms %}
        <a class="btn btn-sm btn-warning mr-1" href="{{record.edit_view_uri}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Edit the metadata of this resource' %}">
          {{ ICONS.EDIT|safe }}
        </a>
        <a class="btn btn-sm btn-warning mr-1" href="{{record.edit_access_view_uri}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Edit the access of this resource' %}">
          {{ ICONS.ACCESS|safe }}
        </a>
        {% endif %}
        {% if record.metadata_type == 'service' %}
            {% if "update_resource" in perms %}
            <a class="btn btn-sm btn-info mr-1" href="{{record.update_view_uri}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Update this resource' %}">
              {{ ICONS.UPDATE|safe }}
            </a>
            {% endif %}
            {% if "add_monitoringrun" in perms %}
            <form class="mr-1" action="{{record.run_monitoring_view_uri}}" method="post">
              {% csrf_token %}
              <input type="hidden"  name="metadatas" value="{{ record.pk }}">
              <button type="submit" class="btn btn-sm btn-info" data-toggle="tooltip" data-placement="left" title="{% trans 'Run monitoring for this resource' %}">{{ ICONS.HEARTBEAT|safe }}</button>
            </form>
            {% endif %}
        {% endif %}
    {% endif %}
    {% if record.metadata_type == 'service' or record.metadata_type == 'catalogue' %}
    {% if "delete_metadata" in perms %}
    <a class="btn btn-sm btn-danger" href="{{record.remove_view_uri}}" role="button" data-toggle="tooltip" data-placement="left" title="{% trans 'Remove this resource' %}">
      {{ ICONS.DELETE|safe }}
    </a>
    {% endif %}
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
