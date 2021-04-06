PENDING_TASK_ACTIONS = """
{% load i18n %}
<div class="d-inline-flex">
    <form class="mr-1" action="{{record.remove_view_uri}}" method="post">
      {% csrf_token %}
      <button type="submit" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="top" title="{% trans 'Cancel task' %}">{{ ICONS.DELETE|safe }}</button>
    </form>
    {% if record.error_report %}
    <a class="btn btn-sm btn-warning" href="{{record.error_report_uri}}" role="button" data-toggle="tooltip" data-placement="top" title="{% trans 'Download the error report as text file.' %}">
      {{ ICONS.CSW|safe }}
    </a>
    {% endif %}
</div>
"""