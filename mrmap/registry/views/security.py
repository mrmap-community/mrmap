from extras.views import SecuredListMixin, SecuredCreateView, SecuredUpdateView, SecuredDeleteView
from registry.filtersets.security import AllowedOperationFilterSet, ServiceAccessGroupFilterSet, AnalyzedResponseLogFilterSet, \
    ExternalAuthenticationFilterSet
from registry.forms.security import ServiceAccessGroupModelForm, ProxySettingModelForm, \
    AllowedOperationPage2ModelForm, ExternalAuthenticationModelForm
from registry.models.security import AllowedOperation, ServiceAccessGroup, ProxySetting, AnalyzedResponseLog, \
    ExternalAuthentication
from registry.tables.security import AllowedOperationTable, ServiceAccessGroupTable, AnalyzedResponseLogTable, \
    ExternalAuthenticationTable, ProxySettingTable
from django_filters.views import FilterView


class ExternalAuthenticationListView(SecuredListMixin, FilterView):
    model = ExternalAuthentication
    table_class = ExternalAuthenticationTable
    filterset_class = ExternalAuthenticationFilterSet


class ExternalAuthenticationAddView(SecuredCreateView):
    model = ExternalAuthentication
    form_class = ExternalAuthenticationModelForm


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


class ServiceAccessGroupChangeView(SecuredUpdateView):
    model = ServiceAccessGroup
    form_class = ServiceAccessGroupModelForm


class ServiceAccessGroupDeleteView(SecuredDeleteView):
    model = ServiceAccessGroup


class AllowedOperationListView(SecuredListMixin, FilterView):
    model = AllowedOperation
    table_class = AllowedOperationTable
    filterset_class = AllowedOperationFilterSet


class AllowedOperationChangeView(SecuredUpdateView):
    model = AllowedOperation
    form_class = AllowedOperationPage2ModelForm


class AllowedOperationDeleteView(SecuredDeleteView):
    model = AllowedOperation


class ProxySettingListView(SecuredListMixin, FilterView):
    model = ProxySetting
    table_class = ProxySettingTable


class ProxySettingCreateView(SecuredCreateView):
    model = ProxySetting
    form_class = ProxySettingModelForm


class ProxySettingUpdateView(SecuredUpdateView):
    model = ProxySetting
    form_class = ProxySettingModelForm


class AnalyzedResponseLogListView(SecuredListMixin, FilterView):
    model = AnalyzedResponseLog
    table_class = AnalyzedResponseLogTable
    filterset_class = AnalyzedResponseLogFilterSet
    queryset = model.objects.for_table_view()
