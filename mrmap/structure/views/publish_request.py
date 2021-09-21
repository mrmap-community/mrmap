from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django_filters.views import FilterView
from MrMap.messages import *
from extras.views import SecuredCreateView, SecuredListMixin, SecuredUpdateView, SecuredDeleteView
from structure.models import PublishRequest
from structure.permissionEnums import PermissionEnum
from structure.tables.tables import PublishesRequestTable


class PublishRequestNewView(SecuredCreateView):
    model = PublishRequest
    fields = ('from_organization', 'to_organization', 'message')
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = PUBLISH_REQUEST_SENT

    # FIXME: find a better solution to handle request keword argument with forms.ModelForm classes
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop("request")
        return kwargs


class PublishRequestTableView(SecuredListMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['from_organization', 'to_organization', 'message']
    permission_required = [PermissionEnum.CAN_VIEW_PUBLISH_REQUEST.value]


class PublishRequestUpdateView(SecuredUpdateView):
    model = PublishRequest
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept request')

    def get_success_url(self):
        return self.object.to_organization.get_absolute_url()

    # FIXME: find a better solution to handle request keword argument with forms.ModelForm classes
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop("request")
        return kwargs


class PublishRequestRemoveView(SecuredDeleteView):
    model = PublishRequest
    success_url = reverse_lazy('structure:index')
    success_message = PUBLISH_REQUEST_DENIED
    title = _('Deny request')
