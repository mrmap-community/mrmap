from django.template import Template, Context

from MrMap.icons import get_all_icons
from extras.template_codes.template_codes import DefaultActionButtonsTemplate


class DefaultActionButtons:
    buttons = ('edit', 'remove')

    def __init__(self, instance, request, pk_field='pk', buttons=None):
        self.instance = instance
        self.request = request
        self.template_code = DefaultActionButtonsTemplate(model=self.instance._meta.model,
                                                          pk_field=pk_field,
                                                          instance_context_var='instance').template_code

        self.extra_context = {
            'instance': self.instance,
            'request': self.request,
            'buttons': buttons if buttons else self.buttons,
            'ICONS': get_all_icons(),
        }

    def render(self):
        context = Context()
        context.update(self.extra_context)

        return Template(template_string=self.template_code).render(context=context)
