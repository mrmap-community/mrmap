from django.urls import reverse_lazy, reverse

from MrMap.messages import *
from guardian_roles.models.core import OwnerBasedRole
from main.views import SecuredUpdateView
from django.utils.translation import gettext_lazy as _


class RoleUpdateView(SecuredUpdateView):
    model = OwnerBasedRole
    fields = ('users', )
    title = _('Edit role')

    def get_success_message(self, cleaned_data):
        cleaned_data.update({'role': self.object.based_template.verbose_name})
        return ROLE_SUCCESSFULLY_EDITED % cleaned_data

    def get_success_url(self):
        return reverse('structure:organization_roles_overview', args=[self.object.content_object.pk])
