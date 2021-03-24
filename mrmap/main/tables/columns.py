import django_tables2 as tables

from django.utils.translation import gettext_lazy as _
from MrMap.icons import get_all_icons


class GenericButtonsColumn(tables.TemplateColumn):
    """
    Render accept and deny buttons for PublishRequest.
    """
    attrs = {'td': {'class': 'text-right text-nowrap noprint'}}
    template_code = None
    model = None
    pk_field = 'pk'

    def __init__(self, *args, **kwargs):
        template_code = self.template_code.format(
            app_label=self.model._meta.app_label,
            model_name=self.model._meta.model_name,
            pk_field=self.pk_field,
        )

        super().__init__(template_code=template_code, *args, **kwargs)

        self.extra_context.update({
            'ICONS': get_all_icons(),
        })

    def header(self):
        return ''


class DefaultActionButtonsColumn(tables.TemplateColumn):
    buttons = ('edit', 'remove')
    attrs = {'td': {'class': 'text-right text-nowrap noprint'}}
    pk_field = 'pk'
    template_code = """
    {{% load static i18n %}}
    {{% load guardian_tags %}}
    
    {{% url '{app_label}:{model_name}_change' {pk_field}=record.{pk_field} as change_url %}}
    {{% if "edit" in buttons and change_url and "change_{model_name}" in perms %}}
    <a href="{{{{change_url}}}}" class="btn btn-sm btn-warning" data-toggle="tooltip" data-placement="left" data-html="true" title="{{% trans 'Edit ' %}}<strong>{{{{record}}}}</strong>">
        {{{{ ICONS.EDIT|safe }}}}
    </a>
    {{% endif %}}
    {{% url '{app_label}:{model_name}_remove' {pk_field}=record.{pk_field} as remove_url %}}
    {{% if "remove" in buttons and remove_url and "remove_{model_name}" in perms %}}
    <a href="{{{{remove_url}}}}" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="left" data-html="true" title="{{% trans 'Remove ' %}}<strong>{{{{record}}}}</strong>">
        {{{{ ICONS.REMOVE|safe }}}}
    </a>
    {{% endif %}}
    """

    def __init__(self, model, *args, **kwargs):
        template_code = self.template_code.format(
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            pk_field=self.pk_field,
            buttons=self.buttons,
        )

        super().__init__(template_code=template_code, orderable=False, *args, **kwargs)

        self.extra_context.update({
            'buttons': self.buttons,
            'ICONS': get_all_icons(),
        })

    def header(self):
        return _('Actions')
