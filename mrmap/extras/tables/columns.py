import django_tables2 as tables

from django.utils.translation import gettext_lazy as _
from MrMap.icons import get_all_icons

from extras.template_codes.template_codes import DefaultActionButtonsTemplate


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

        super().__init__(template_code=template_code, orderable=False, *args, **kwargs)

        self.extra_context.update({
            'ICONS': get_all_icons(),
        })

    def header(self):
        return _('Actions')


class DefaultActionButtonsColumn(tables.TemplateColumn):
    buttons = ('edit', 'remove')
    attrs = {'td': {'class': 'text-right text-nowrap noprint'}}
    pk_field = 'pk'

    def __init__(self, model, pk_field='pk', *args, **kwargs):
        template_code = DefaultActionButtonsTemplate(model=model,
                                                     pk_field=pk_field,
                                                     instance_context_var='record').template_code

        super().__init__(template_code=template_code, orderable=False, *args, **kwargs)

        self.extra_context.update({
            'buttons': self.buttons,
            'ICONS': get_all_icons(),
        })

    def header(self):
        return _('Actions')
