from main.views import SecuredListMixin, SecuredCreateView, SecuredUpdateView
from resourceNew.filtersets.security import AllowedOperationFilterSet, ServiceAccessGroupFilterSet, ProxyLogFilterSet
from resourceNew.forms.security import ServiceAccessGroupModelForm, ProxySettingModelForm, \
    AllowedOperationPage2ModelForm
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxySetting, ProxyLog
from resourceNew.tables.security import AllowedOperationTable, ServiceAccessGroupTable, ProxyLogTable
from django_filters.views import FilterView
from django.urls import reverse_lazy


class ServiceAccessGroupListView(SecuredListMixin, FilterView):
    model = ServiceAccessGroup
    table_class = ServiceAccessGroupTable
    filterset_class = ServiceAccessGroupFilterSet


class ServiceAccessGroupCreateView(SecuredCreateView):
    model = ServiceAccessGroup
    form_class = ServiceAccessGroupModelForm
    # success_message = MAP_CONTEXT_SUCCESSFULLY_CREATED
    success_url = reverse_lazy('resourceNew:service_access_group_list')


class AllowedOperationListView(SecuredListMixin, FilterView):
    model = AllowedOperation
    table_class = AllowedOperationTable
    filterset_class = AllowedOperationFilterSet


class AllowedOperationChangeView(SecuredUpdateView):
    model = AllowedOperation
    form_class = AllowedOperationPage2ModelForm


class ProxySettingCreateView(SecuredCreateView):
    model = ProxySetting
    form_class = ProxySettingModelForm
    # success_message = MAP_CONTEXT_SUCCESSFULLY_CREATED
    success_url = reverse_lazy('resourceNew:proxy_setting_list')


class ProxyLogListView(SecuredListMixin, FilterView):
    model = ProxyLog
    table_class = ProxyLogTable
    filterset_class = ProxyLogFilterSet
