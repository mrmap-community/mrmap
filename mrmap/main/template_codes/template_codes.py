PERMISSIONS = """
{% for perm in value %}
<span class="badge badge-info">{{perm.name}}</span>
{% endfor %}
"""


class DefaultActionButtonsTemplate:
    template_code = """
    {{% load static i18n %}}
    {{% load guardian_tags %}}
    {{% get_obj_perms request.user for {instance_context_var} as "obj_perms" %}}

    {{% url '{app_label}:{model_name}_change' {pk_field}={instance_context_var}.{pk_field} as change_url %}}
    {{% if "edit" in buttons and change_url and "change_{model_name}" in obj_perms %}}
    <a href="{{{{change_url}}}}" class="btn btn-sm btn-warning" data-toggle="tooltip" data-placement="left" data-html="true" title="{{% trans 'Edit ' %}}<strong>{{{{{instance_context_var}}}}}</strong>">
        {{{{ ICONS.EDIT|safe }}}}
    </a>
    {{% endif %}}
    {{% url '{app_label}:{model_name}_remove' {pk_field}={instance_context_var}.{pk_field} as remove_url %}}
    {{% if "remove" in buttons and remove_url and "remove_{model_name}" in obj_perms %}}
    <a href="{{{{remove_url}}}}" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="left" data-html="true" title="{{% trans 'Remove ' %}}<strong>{{{{{instance_context_var}}}}}</strong>">
        {{{{ ICONS.REMOVE|safe }}}}
    </a>
    {{% endif %}}
    """

    def __init__(self, model, instance_context_var, pk_field='pk'):
        self.template_code = self.template_code.format(
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            pk_field=pk_field,
            instance_context_var=instance_context_var
        )
