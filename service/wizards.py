from django.http import HttpResponseRedirect
from django.urls import reverse
from MrMap.wizards import MrMapWizard
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from service.forms import RegisterNewResourceWizardPage1, RegisterNewResourceWizardPage2
from service.helper import service_helper

NEW_RESOURCE_WIZARD_FORMS = [(_("Service url"), RegisterNewResourceWizardPage1),
                             (_("overview"), RegisterNewResourceWizardPage2), ]


class NewResourceWizard(MrMapWizard):
    def __init__(self, current_view, *args, **kwargs):
        super(MrMapWizard, self).__init__(
            action_url=reverse('resource:add', ) + f"?current-view={current_view}",
            current_view=current_view,
            *args,
            **kwargs)

    def get_form_initial(self, step):
        initial = self.initial_dict.get(step, {})

        if step == "overview":
            service_url_data = self.storage.get_step_data('Service url')
            uri = service_url_data.get('Service url-get_request_uri')
            url_dict = service_helper.split_service_uri(uri)
            initial.update({
                'ogc_request': url_dict["request"],
                'ogc_service': url_dict["service"].value,
                'ogc_version': url_dict["version"],
                'uri': url_dict["base_uri"],
                'service_needs_authentication': False,
            })
        return initial

    def done(self, form_list, **kwargs):
        """ Iterates over all forms and fills the Metadata/Dataset records accordingly

        Args:
            form_list (FormList): An iterable list of forms
            kwargs:
        Returns:

        """
        for form in form_list:
            if isinstance(form, RegisterNewResourceWizardPage2):
                try:
                    # Run creation async!
                    # Function returns the pending task object
                    service_helper.create_new_service(form, form.requesting_user)
                except Exception as e:
                    messages.error(self.request, message=e)
                    return HttpResponseRedirect(reverse(self.current_view, ), status=303)

        return HttpResponseRedirect(reverse(self.current_view, ), status=303)
