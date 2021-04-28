from django_filters.views import FilterView
from MrMap.messages import ACCESS_CONTROL_LIST_SUCCESSFULLY_EDITED, ACCESS_CONTROL_LIST_SUCCESSFULLY_CREATED
from acl.forms import AccessControlListChangeForm
from acl.models.acl import AccessControlList
from acl.tables import AccessControlListTable
from main.views import SecuredListMixin, SecuredUpdateView, SecuredCreateView


class AccessControlListTableView(SecuredListMixin, FilterView):
    model = AccessControlList
    table_class = AccessControlListTable
    filterset_fields = ('__all__')
    accept_global_perms = False


class AccessControlListCreateView(SecuredCreateView):
    model = AccessControlList
    form_class = AccessControlListChangeForm
    success_message = ACCESS_CONTROL_LIST_SUCCESSFULLY_CREATED
    accept_global_perms = True


class AccessControlListUpdateView(SecuredUpdateView):
    model = AccessControlList
    form_class = AccessControlListChangeForm
    success_message = ACCESS_CONTROL_LIST_SUCCESSFULLY_EDITED
