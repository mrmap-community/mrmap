SERVICE_DETAIL_ICONS = """
{% load i18n %}
{% if record.get_detail_url %}
<a href="{{record.get_detail_url}}?vk=tree" data-toggle="tooltip" data-placement="left" title="{% trans 'Show tree view' %}">{{ICONS.HIERARCHY}}</a>
{% endif %}
</div>
"""
