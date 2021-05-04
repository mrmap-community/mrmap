PENDING_TASK_ACTIONS = """
{% load i18n %}
<div class="d-inline-flex">
    {% if record.status not in 'SUCCESS,FAILURE,REVOKED' %}
    <form class="mr-1" action="{% url 'structure:remove-task' record.pk %}" method="post">
      {% csrf_token %}
      <button type="submit" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="top" title="{% trans 'Cancel task' %}">{{ ICONS.DELETE|safe }}</button>
    </form>
    {% endif %}
    {% if record.status == 'FAILURE' %}
    <a class="btn btn-sm btn-warning" href="{% url 'structure:generate-error-report' record.pk %}" role="button" data-toggle="tooltip" data-placement="top" title="{% trans 'Download the error report as text file.' %}">
      {{ ICONS.CSW|safe }}
    </a>
    {% endif %}
</div>
"""