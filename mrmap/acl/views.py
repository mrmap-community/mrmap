from django_filters.views import FilterView

from MrMap.messages import ACCESS_CONTROL_LIST_SUCCESSFULLY_EDITED
from acl.forms import AccessControlListChangeForm
from acl.models.acl import AccessControlList
from acl.tables import AccessControlListTable
from main.views import SecuredListMixin, SecuredUpdateView


class AccessControlListTableView(SecuredListMixin, FilterView):
    model = AccessControlList
    table_class = AccessControlListTable
    filterset_fields = {'__all__'}


class AccessControlListUpdateView(SecuredUpdateView):
    model = AccessControlList
    template_name = "MrMap/detail_views/generic_form.html"
    form_class = AccessControlListChangeForm
    success_message = ACCESS_CONTROL_LIST_SUCCESSFULLY_EDITED
