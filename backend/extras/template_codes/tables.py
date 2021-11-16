EDIT_DELETE_BUTTON = """
{% load i18n %}
{% load guardian_tags %}
{{% get_obj_perms request.user for record as "obj_perms" %}}
<a href="{{record.change_view_uri}}" class="btn btn-sm btn-warning" data-toggle="tooltip" data-placement="left" data-html="true" title="{% trans 'Edit ' %}<strong>{{record}}</strong>">
    {{ ICONS.EDIT|safe }}
</a>
<a href="{{record.delete_view_uri}}" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="left" data-html="true" title="{% trans 'Edit ' %}<strong>{{record}}</strong>">
    {{ ICONS.DELETE|safe }}
</a>
"""
