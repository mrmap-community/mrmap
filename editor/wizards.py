from django.http import HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse, resolve
from formtools.wizard.views import SessionWizardView
from MapSkinner.utils import get_theme
from editor.forms import DatasetIdentificationForm, DatasetClassificationForm
from users.helper import user_helper

DATASET_WIZARD_FORMS = [("identification", DatasetIdentificationForm), ("classification", DatasetClassificationForm)]


class DatasetWizard(SessionWizardView):
    template_name = "sceletons/modal-wizard-form.html"

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context.update({'id_modal': self.kwargs['id_modal'],
                        'modal_title': self.kwargs['title'],
                        'THEME': get_theme(user_helper.get_user(self.request)),
                        'action_url': reverse('editor:dataset-metadata-wizard-instance',
                                              args=(form.current_view, self.kwargs.get('instance_id')))
                        if 'instance_id' in self.kwargs else reverse('editor:dataset-metadata-wizard-new',
                                                                     args=(form.current_view,)),
                        'show_modal': True,
                        'fade_modal': True,
                        'current_view': self.kwargs['current_view'],
                        })

        if bool(self.storage.data['step_data']):
            # this wizard is not new, prevent from bootstrap modal fading
            context.update({'fade_modal': False, })

        return context

    def render(self, form=None, **kwargs):
        form = form or self.get_form()
        context = self.get_context_data(form=form, **kwargs)

        rendered_wizard = render_to_string(request=self.request,
                                           template_name=self.template_name,
                                           context=context)

        view_function = resolve(reverse(f'{form.current_view}', ))
        rendered_view = view_function.func(request=self.request, rendered_wizard=rendered_wizard)

        return rendered_view

    def get_form_kwargs(self, step):
        return {'current_view': self.kwargs['current_view'],
                'instance_id': self.kwargs['instance_id'] if 'instance_id' in self.kwargs else None,
                'request': self.request, }

    def done(self, form_list, **kwargs):
        for form in form_list:
            # ToDo: save input of all forms
            i = 0
            pass

        return HttpResponseRedirect(reverse(self.kwargs['current_view'], ), status=303)
