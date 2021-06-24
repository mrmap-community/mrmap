from abc import ABC
from formtools.wizard.views import SessionWizardView
from django.shortcuts import redirect

from resourceNew.forms.security import AllowedOperationPage1ModelForm, AllowedOperationPage2ModelForm


ALLOWED_OPERATION_WIZARD_FORMS = [("secured_service", AllowedOperationPage1ModelForm),
                                  ("allowed_operation", AllowedOperationPage2ModelForm)]


class AllowedOperationWizard(SessionWizardView, ABC):
    template_name = "generic_views/base_extended/wizard.html"

    def get_form_kwargs(self, step=None):
        return {"request": self.request}

    def get_form_step_data(self, form):
        data = form.data
        if isinstance(form, AllowedOperationPage1ModelForm):
            self.initial_dict.update({"allowed_operation": {"secured_service": data.get(f"{form.prefix}-secured_service")}})
        return data

    def done(self, form_list, **kwargs):
        obj = form_list[-1].save()
        return redirect(to=obj.get_concrete_table_url())
