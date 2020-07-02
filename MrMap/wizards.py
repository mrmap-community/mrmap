from abc import ABC
from django.template.loader import render_to_string
from django.urls import reverse, resolve
from formtools.wizard.views import SessionWizardView
from MrMap.utils import get_theme
from users.helper import user_helper
from django.utils.translation import gettext_lazy as _


class MrMapWizard(SessionWizardView, ABC):
    template_name = "sceletons/modal-wizard-form.html"
    ignore_uncomitted_forms = False
    current_view = None
    instance_id = None
    title = None
    id_wizard = None
    required_forms = None

    def __init__(self,
                 current_view: str,
                 instance_id: int = None,
                 ignore_uncomitted_forms: bool = False,
                 required_forms: list = None,
                 title: str = _('Wizard'),
                 # ToDo: random id for wizard as default
                 id_wizard: str = 'id_wizard',
                 *args,
                 **kwargs):
        super(MrMapWizard, self).__init__(*args, **kwargs)
        self.current_view = current_view
        self.instance_id = instance_id
        self.ignore_uncomitted_forms = ignore_uncomitted_forms
        self.required_forms = required_forms
        self.title = title
        self.id_wizard = id_wizard

    def get_context_data(self, form, **kwargs):
        context = super(MrMapWizard, self).get_context_data(form=form, **kwargs)
        context.update({'id_modal': self.id_wizard,
                        'modal_title': self.title,
                        'THEME': get_theme(user_helper.get_user(self.request)),
                        'action_url': reverse('editor:dataset-metadata-wizard-instance',
                                              args=(self.current_view, self.instance_id))
                        if self.instance_id else reverse('editor:dataset-metadata-wizard-new',
                                                         args=(self.current_view,)),
                        'show_modal': True,
                        'fade_modal': True,
                        'current_view': self.current_view,
                        })
        context['wizard'].update({'ignore_uncomitted_forms': self.ignore_uncomitted_forms})

        if bool(self.storage.data['step_data']):
            # this wizard is not new, prevent from bootstrap modal fading
            context.update({'fade_modal': False, })

        return context

    def render(self, form=None, **kwargs):
        # we implement custom rendering, for that we need the current we to render the modal as string and
        # pass it to the view where the wizard should be rendered
        form = form or self.get_form()
        context = self.get_context_data(form=form, **kwargs)

        rendered_wizard = render_to_string(request=self.request,
                                           template_name=self.template_name,
                                           context=context)

        view_function = resolve(reverse(f"{self.current_view}", ))
        return view_function.func(request=self.request, update_params={'rendered_modal': rendered_wizard})

    def render_goto_step(self, goto_step, **kwargs):
        # 1. save current form, we doesn't matter for validation for now.
        # If the wizard is done, he will perform validation for each.
        current_form = self.get_form(data=self.request.POST, files=self.request.FILES)
        self.storage.set_step_data(self.steps.current,
                                   self.process_step(current_form))
        self.storage.set_step_files(self.steps.current, self.process_step_files(current_form))

        if self.storage.current_step == goto_step and \
                f"{current_form.prefix}-is_form_update" in self.request.POST and \
                self.request.POST[f"{current_form.prefix}-is_form_update"] == 'True':
            return self.render(current_form)
        return super(MrMapWizard, self).render_goto_step(goto_step=goto_step)

    def process_step(self, form):
        # we implement custom logic to ignore uncomitted forms,
        # but if the uncomitted form is required, then we dont drop it
        if self.ignore_uncomitted_forms and 'wizard_save' in self.request.POST:
            uncomitted_forms = []
            for form_key in self.get_form_list():
                form_obj = self.get_form(
                    step=form_key,
                    data=self.storage.get_step_data(form_key),
                    files=self.storage.get_step_files(form_key)
                )
                # x.1. self.get_form_list(): get the unbounded forms
                if not form_obj.is_bound and form_key != self.steps.current:
                    uncomitted_forms.append(form_key)
            # x.4. if no unbounded form has required fields then remove them from the form_list
            temp_form_list = self.form_list
            for uncomitted_form in uncomitted_forms:
                # only pop non required forms
                if self.required_forms is None or uncomitted_form not in self.required_forms:
                    self.form_list.pop(uncomitted_form)
                else:
                    # there was an uncomitted required form. Go the default way
                    self.form_list = temp_form_list
                    return self.get_form_step_data(form)
            # set current commited form as last form
            self.form_list.move_to_end(self.steps.current)
        return self.get_form_step_data(form)

    def get_form_kwargs(self, step):
        # pass instance_id and request to the forms
        return {'instance_id': self.instance_id,
                'request': self.request, }
