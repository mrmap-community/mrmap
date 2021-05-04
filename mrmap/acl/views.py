from django_filters.views import FilterView
from MrMap.messages import ACCESS_CONTROL_LIST_SUCCESSFULLY_EDITED, ACCESS_CONTROL_LIST_SUCCESSFULLY_CREATED
from acl.forms import AccessControlListChangeForm
from acl.models.acl import AccessControlList
from acl.tables import AccessControlListTable, AccessControlListDetailTable
from main.views import SecuredListMixin, SecuredUpdateView, SecuredCreateView, SecuredDetailView
from django.utils.translation import gettext as _


class AccessControlListTableView(SecuredListMixin, FilterView):
    model = AccessControlList
    table_class = AccessControlListTable
    filterset_fields = ('__all__')
    accept_global_perms = False

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs).\
            select_related('owned_by_org').\
            prefetch_related('permissions', 'user_set')
        return qs


class AccessControlListDetailView(SecuredDetailView):
    class Meta:
        verbose_name = _('Details')

    model = AccessControlList
    title = _('Details')
    template_name = 'MrMap/detail_views/table_tab.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = AccessControlListDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


class AccessControlListUpdateView(SecuredUpdateView):
    model = AccessControlList
    form_class = AccessControlListChangeForm
    success_message = ACCESS_CONTROL_LIST_SUCCESSFULLY_EDITED
