VALUE_ABSOLUTE_LINK = """
<a href="{{value.get_absolute_url}}">{{value}}</a>
"""

VALUE_ABSOLUTE_LINK_LIST = """
{% for val in value %}
<a href="{{val.get_absolute_url}}">{{val}}</a>,
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
{% if record.use_proxy_uri %}<span class="">{{ICONS.PROXY}}</span>{% endif %}
{% if record.log_proxy_access %}<span class="">{{ICONS.LOGGING}}</span>{% endif %}
{% if record.is_secured %}<a class="btn btn-sm btn-outline-info" href="record.security_overview_uri">{{ICONS.WFS}}</a>{% endif %}
{% if record.external_authentication %}{{ICONS.PASSWORD}}{% endif %}
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