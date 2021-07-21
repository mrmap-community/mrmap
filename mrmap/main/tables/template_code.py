VALUE_ABSOLUTE_LINK = """
{% if value.get_absolute_url%}
<a href="{{value.get_absolute_url}}">{{value}}</a>
{% else %}
{{value}}
{% endif %}
"""

VALUE_TABLE_LINK = """
{% if value.get_table_url %}
<a href="{{value.get_table_url}}">{{value}}</a>
{% else %}
{{value}}
{% endif %}
"""

VALUE_CONCRETE_TABLE_LINK = """
{% if value.get_concrete_table_url %}
<a href="{{value.get_concrete_table_url}}">{{value}}</a>
{% else %}
{{value}}
{% endif %}
"""

VALUE_ABSOLUTE_LINK_LIST = """
{% for val in value %}
<a href="{{val.get_table_url}}">{{val}}</a>,
{% endfor %}
"""

RECORD_ABSOLUTE_LINK = """
{% if record.get_absolute_url %}<a href="{{record.get_absolute_url}}">{{record}}</a>{% else %}{{record}}{% endif %}
"""

RECORD_ABSOLUTE_LINK_VALUE_CONTENT = """
{% if record.get_absolute_url %}<a href="{{record.get_absolute_url}}">{{value}}</a>{% else %}{{value}}{% endif %}
"""


VALUE_BADGE = """
<span class="badge {% if color %}{{color}}{% else %}badge-info{% endif %}">{{value}}</span>
"""

VALUE_BADGE_LIST = """
{% for val in value %}
<span class="badge {% if color %}{{color}}{% else %}badge-info{% endif %}">{{val}}</span>
{% endfor %}
"""

SERVICE_STATUS_ICONS = """
{% load i18n %}
<span class="{% if record.is_active %}text-success{% else %}text-danger{% endif %}">{{ICONS.POWER_OFF}}</span>
{% if record.proxy_setting.camouflage %}<span class="">{{ICONS.PROXY}}</span>{% endif %}
{% if record.proxy_setting.log_response %}<span class="">{{ICONS.LOGGING}}</span>{% endif %}
{% if record.is_secured %}
<span class="d-inline-block" tabindex="0" data-toggle="tooltip" data-placement="left" title="{% trans 'This service is secured spatial' %}">
<a href="
{% for allowed_operation in record.allowed_operations.all %}
{% if forloop.first %}
{{allowed_operation.get_table_url}}
{% else %}
,{{allowed_operation.pk}}
{% endif %}
{% endfor %}
">{{ICONS.ALLOWED_OPERATION}}</a>
</span>
{% endif %}
{% if record.external_authentication %}
<span class="d-inline-block" tabindex="0" data-toggle="tooltip" data-placement="left" title="{% trans 'This service uses an authentication' %}">
<a href="{{record.external_authentication.get_table_url}}">{{record.external_authentication.icon}}</a>
</span>
{% endif %}
"""

SERVICE_HEALTH_ICONS = """
{% load i18n %}
{% with record.get_health_state as health_state %}
{% if health_state %}
    {% if health_state.health_state_code == 'unknown' %}
        <span class="text-secondary">{{ICONS.HEARTBEAT}}</span>
    {% else %}
        <a href="health_state.get_absolute_url" class="{% if health_state.health_state_code == 'ok' %}btn-outline-success{% elif health_state.health_state_code == 'warning' %}btn-outline-warning{% elif health_state.health_state_code == 'critical' %}btn-outline-danger{% endif %}">
            {{ICONS.HEARTBEAT}}
        </a>
        <span class="badge {% if health_state.reliability_1w < CRITICAL_RELIABILITY %}badge-danger{% elif health_state.reliability_1w < WARNING_RELIABILITY %}badge-warning{% endif %}">{{health_state.reliability_1w}} %</span>
    {% endif %}
{% else %}
    <span class="text-secondary">{{ICONS.HEARTBEAT}}</span>
{% endif %}
{% endwith %}
"""

DEFAULT_ACTION_BUTTONS = """
{% load i18n %}
{% load guardian_tags %}
{% load custom_template_filters %}
{% get_obj_perms request.user for record as "perms" table.perm_checker %}
<div class="d-inline-flex">
    {% with record|to_class_name|lower as model_name %}
    {% if "change_"|add:model_name in perms and record.get_change_url %}
    <a href="{{record.get_change_url}}" class="btn btn-sm btn-warning mr-1" data-toggle="tooltip" data-placement="left" title="{% trans 'Edit' %}">{{ ICONS.EDIT|safe }}</a>
    {% endif %}
    {% if "change_"|add:model_name in perms and record.get_restore_url and record.is_customized %}
    <a href="{{record.get_restore_url}}" class="btn btn-sm btn-danger mr-1" data-toggle="tooltip" data-placement="left" title="{% trans 'Restore' %}">{{ ICONS.RESTORE|safe }}</a>
    {% endif %}
    {% if "delete_"|add:model_name in perms and record.get_delete_url %}
    <a href="{{record.get_delete_url}}" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="left" title="{% trans 'Delete' %}">{{ ICONS.DELETE|safe }}</a>
    {% endif %}
    {% if record.get_validate_url %}
    <a href="{{record.get_validate_url}}" class="btn btn-sm btn-primary" data-toggle="tooltip" data-placement="left" title="{% trans 'Validate' %}">{{ ICONS.VALIDATION }}</a>
    {% endif %}    
    {% endwith %}
</div>
"""
OPERATION_URLS = """
{% load i18n %}
<button type="button" class="btn btn-sm btn-info" data-container="body" data-toggle="popover" title="{% trans 'Operation urls' %}" data-html="true" data-content="{% for url in value %}<a href='{{url.concrete_url}}'>{{url.operation}} ({{url.method}})</a><br>{% endfor %}">{% trans 'details' %}</button>
"""
