from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django_filters.views import FilterView
from MrMap.messages import *
from main.views import SecuredCreateView, SecuredListMixin, SecuredUpdateView, SecuredDeleteView
from structure.models import PublishRequest
from structure.permissionEnums import PermissionEnum
from structure.tables.tables import PublishesRequestTable


class PublishRequestNewView(SecuredCreateView):
    model = PublishRequest
    fields = ('from_organization', 'to_organization', 'message')
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('Publish request')
    success_message = PUBLISH_REQUEST_SENT


class PublishRequestTableView(SecuredListMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['from_organization', 'to_organization', 'message']
    permission_required = [PermissionEnum.CAN_VIEW_PUBLISH_REQUEST.value]


class PublishRequestUpdateView(SecuredUpdateView):
    model = PublishRequest
    template_name = "MrMap/detail_views/generic_form.html"
    success_url = reverse_lazy('structure:publish_request_overview')
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept request')

    def get_success_url(self):
        return self.object.to_organization.get_absolute_url()


class PublishRequestRemoveView(SecuredDeleteView):
    model = PublishRequest
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:index')
    success_message = PUBLISH_REQUEST_DENIED
    title = _('Deny request')
