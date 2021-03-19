from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from MrMap.wizards import MrMapWizard
from django.utils.translation import gettext_lazy as _
from guardian_roles.forms import OrganizationModelForm, TemplateRoleSelection
from guardian_roles.models.core import OrganizationBasedTemplateRole

FIRST_STEP_ID = _("Organization")
SECOND_STEP_ID = _("Administrative roles")

CREATE_ORGANIZATION_WIZARD_FORMS = [
    (FIRST_STEP_ID, OrganizationModelForm),
    (SECOND_STEP_ID, TemplateRoleSelection),
]


@method_decorator(login_required, name='dispatch')
class CreateOrganizationWizard(MrMapWizard):
    # todo: who can create Organizations?
    success_url = reverse_lazy('resource:pending-tasks')  # todo: set to get_absolute_url() of the generated Organization
    title = '<strong>Create new Organization</strong>'
    organization = None

    def done(self, form_list, **kwargs):
        for form in form_list:
            if isinstance(form, OrganizationModelForm):
                self.organization = form.save()
            elif isinstance(form, TemplateRoleSelection):
                for template in form.cleaned_data['based_templates']:
                    OrganizationBasedTemplateRole.objects.create(content_object=self.organization,
                                                                 based_template=template)
        return super().done(form_list, **kwargs)
