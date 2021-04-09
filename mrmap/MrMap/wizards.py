import uuid
from abc import ABC

from django.core.exceptions import ImproperlyConfigured
from django.forms import BaseFormSet, modelformset_factory, HiddenInput
from django.shortcuts import redirect
from formtools.wizard.views import SessionWizardView
from django.utils.translation import gettext_lazy as _
from django.forms.formsets import DELETION_FIELD_NAME


APPEND_FORM_LOOKUP_KEY = "APPEND_FORM"


def get_class( kls ):
    parts = kls.split('.')
    module = ".".join(parts[:-1])
    m = __import__( module )
    for comp in parts[1:]:
        m = getattr(m, comp)
    return m


class MrMapWizard(SessionWizardView, ABC):
    template_name = "generic_views/base_extended/wizard.html"
    ignore_uncomitted_forms = False
    instance_id = None
    title = _('Wizard')
    id_wizard = "id_" + str(uuid.uuid4())
    required_forms = None
    action_url = ""
    success_url = ""

    def get_success_url(self):
        if self.success_url:
            return self.success_url
        else:
            raise ImproperlyConfigured(
                "No URL to redirect to. Provide a success_url.")

    def get_context_data(self, form, **kwargs):
        context = super(MrMapWizard, self).get_context_data(form=form, **kwargs)

        context.update({'id_modal': self.id_wizard,
                        'modal_title': self.title,
                        'action_url': self.action_url,
                        })
        context['wizard'].update({'ignore_uncomitted_forms': self.ignore_uncomitted_forms})
        return context

    def is_form_update(self):
        if 'is_form_update' in self.request.POST:
            # it's update of dropdown items or something else
            # refresh with updated form
            return True
        return False

    def is_append_formset(self, form):
        if issubclass(form.__class__, BaseFormSet):
            # formset is posted
            append_form_lookup_key = f"{form.prefix}-{APPEND_FORM_LOOKUP_KEY}" if form.prefix else APPEND_FORM_LOOKUP_KEY
            if append_form_lookup_key in form.data:
                # to prevent data loses, we have to store the current form
                self.storage.set_step_data(self.steps.current, self.process_step(form))
                self.storage.set_step_files(self.steps.current, self.process_step_files(form))

                # append current initial_dict to initial new form also
                current_extra = len(form.extra_forms)
                new_init_list = []
                for i in range(current_extra + 1):
                    new_init_list.append(self.initial_dict[self.steps.current][0])
                self.initial_dict[self.steps.current] = new_init_list

                # overwrite new generated forms to form list
                self.form_list[self.steps.current] = modelformset_factory(form.form.Meta.model,
                                                                          can_delete=True,
                                                                          # be carefully; there could also be other Form
                                                                          # classes
                                                                          form=form.forms[0].__class__,
                                                                          extra=current_extra + 1)

                return True
        return False

    def render_next_step(self, form, **kwargs):
        if self.is_append_formset(form=form):
            # call form again with get_form(), cause it is updated and the current form instance does not hold updates
            return self.render(form=self.get_form(step=self.steps.current))
        if self.is_form_update():
            return self.render(form=form)
        return super().render_next_step(form=form, **kwargs)

    def render_done(self, form, **kwargs):
        if self.is_append_formset(form=form):
            # call form again with get_form(), cause it is updated and the current form instance does not hold updates
            return self.render(form=self.get_form(step=self.steps.current))
        if self.is_form_update():
            return self.render(form=form)
        return super().render_done(form=form, **kwargs)

    def render_goto_step(self, goto_step, **kwargs):
        current_form = self.get_form(data=self.request.POST, files=self.request.FILES)
        if self.is_append_formset(form=current_form):
            # call form again with get_form(), cause it is updated and the current form instance does not hold updates
            return self.render(form=self.get_form(step=self.steps.current))
        if self.is_form_update():
            return self.render(current_form)
        # 1. save current form, we doesn't matter for validation for now.
        # If the wizard is done, he will perform validation for each.
        self.storage.set_step_data(self.steps.current,
                                   self.process_step(current_form))
        self.storage.set_step_files(self.steps.current, self.process_step_files(current_form))
        return super().render_goto_step(goto_step=goto_step)

    def process_step(self, form):
        # we implement custom logic to ignore uncomitted forms,
        # but if the uncomitted form is required, then we don't drop it
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

            for uncomitted_form in uncomitted_forms:
                if uncomitted_form in self.required_forms:
                    # not all required forms are posted. Render next form.
                    return self.get_form_step_data(form)
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

    def get_form(self, step=None, data=None, files=None):
        form = super().get_form(step=step, data=data, files=files)
        if issubclass(form.__class__, BaseFormSet) and form.can_delete:
            for _form in form.forms:
                _form.fields[DELETION_FIELD_NAME].widget = HiddenInput()
        return form

    def done(self, form_list, **kwargs):
        return redirect(to=self.get_success_url())