from main.views import SecuredListMixin, SecuredCreateView, SecuredUpdateView, SecuredDeleteView
from resourceNew.filtersets.security import AllowedOperationFilterSet, ServiceAccessGroupFilterSet, ProxyLogFilterSet, \
    ExternalAuthenticationFilterSet
from resourceNew.forms.security import ServiceAccessGroupModelForm, ProxySettingModelForm, \
    AllowedOperationPage2ModelForm, ExternalAuthenticationModelForm
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxySetting, ProxyLog, \
    ExternalAuthentication
from resourceNew.tables.security import AllowedOperationTable, ServiceAccessGroupTable, ProxyLogTable, \
    ExternalAuthenticationTable, ProxySettingTable
from django_filters.views import FilterView
from django.urls import reverse_lazy


class ExternalAuthenticationListView(SecuredListMixin, FilterView):
    model = ExternalAuthentication
    table_class = ExternalAuthenticationTable
    filterset_class = ExternalAuthenticationFilterSet


class ExternalAuthenticationAddView(SecuredCreateView):
    model = ExternalAuthentication
    form_class = ExternalAuthenticationModelForm
    success_url = reverse_lazy('resourceNew:external_authentication_list')


class ExternalAuthenticationChangeView(SecuredUpdateView):
    model = ExternalAuthentication
    form_class = ExternalAuthenticationModelForm


class ExternalAuthenticationDeleteView(SecuredDeleteView):
    model = ExternalAuthentication


class ServiceAccessGroupListView(SecuredListMixin, FilterView):
    model = ServiceAccessGroup
    table_class = ServiceAccessGroupTable
    filterset_class = ServiceAccessGroupFilterSet


class ServiceAccessGroupCreateView(SecuredCreateView):
    model = ServiceAccessGroup
    form_class = ServiceAccessGroupModelForm
    success_url = reverse_lazy('resourceNew:service_access_group_list')


class AllowedOperationListView(SecuredListMixin, FilterView):
    model = AllowedOperation
    table_class = AllowedOperationTable
    filterset_class = AllowedOperationFilterSet


class AllowedOperationChangeView(SecuredUpdateView):
    model = AllowedOperation
    form_class = AllowedOperationPage2ModelForm


class ProxySettingListView(SecuredListMixin, FilterView):
    model = ProxySetting
    table_class = ProxySettingTable


class ProxySettingCreateView(SecuredCreateView):
    model = ProxySetting
    form_class = ProxySettingModelForm
    #success_url = reverse_lazy('resourceNew:proxy_setting_list')


class ProxySettingUpdateView(SecuredUpdateView):
    model = ProxySetting
    form_class = ProxySettingModelForm
    #success_url = reverse_lazy('resourceNew:proxy_setting_list')


class ProxyLogListView(SecuredListMixin, FilterView):
    model = ProxyLog
    table_class = ProxyLogTable
    filterset_class = ProxyLogFilterSet
