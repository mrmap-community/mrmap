from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect
from django.db.models import Q
from django_bootstrap_swt.components import Tag
from django_bootstrap_swt.utils import RenderHelper
from django_filters.views import FilterView
from MrMap.forms import get_current_view_args
from MrMap.icons import IconEnum
from MrMap.messages import METADATA_RESTORING_SUCCESS, RESOURCE_EDITED
from editor.filters import AllowedOperationFilter
from editor.forms import MetadataEditorForm
from editor.tables import AllowedOperationTable
from main.views import SecuredDeleteView, SecuredUpdateView, SecuredConfirmView, SecuredListMixin
from service.helper.enums import MetadataEnum
from service.models import Metadata, AllowedOperation
from structure.permissionEnums import PermissionEnum


class DatasetDelete(SecuredDeleteView):
    model = Metadata
    success_url = reverse_lazy('resource:datasets-index')
    template_name = 'MrMap/detail_views/delete.html'
    queryset = Metadata.objects.filter(metadata_type=MetadataEnum.DATASET.value)
    success_message = _("Dataset successfully deleted.")
    permission_required = PermissionEnum.CAN_REMOVE_DATASET_METADATA.value

    def get_title(self):
        return _("Remove " + self.get_object().__str__())


class EditMetadata(SecuredUpdateView):
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = RESOURCE_EDITED
    model = Metadata
    form_class = MetadataEditorForm
    queryset = Metadata.objects.filter(~Q(metadata_type=MetadataEnum.CATALOGUE.value) |
                                       ~Q(metadata_type=MetadataEnum.DATASET.value))


class RestoreMetadata(SecuredConfirmView):
    model = Metadata
    no_cataloge_type = ~Q(metadata_type=MetadataEnum.CATALOGUE.value)
    is_custom = Q(is_custom=True)
    queryset = Metadata.objects.filter(is_custom | no_cataloge_type)
    success_message = METADATA_RESTORING_SUCCESS

    def get_title(self):
        return _("Restore ").__str__() + self.object.__str__()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"is_confirmed_label": _("Do you really want to restore Metadata?")})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "action_url": self.object.restore_view_uri,
        })
        return context

    def form_valid(self, form):
        self.object = self.get_object()
        ext_auth = self.object.get_external_authentication_object()
        self.object.restore(self.object.identifier, external_auth=ext_auth)

        success_url = self.get_success_url()

        return HttpResponseRedirect(success_url)


class AllowedOperationTableView(SecuredListMixin, FilterView):
    model = AllowedOperation
    table_class = AllowedOperationTable
    filterset_class = AllowedOperationFilter
    template_name = 'generic_views/generic_list_with_base.html'
    root_metadata = None

    def dispatch(self, request, *args, **kwargs):
        self.root_metadata = get_object_or_404(Metadata, id=kwargs.get('pk', None))
        return super(AllowedOperationTableView, self).dispatch(request, *args, **kwargs)

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(AllowedOperationTableView, self).get_table(**kwargs)

        table.title = Tag(tag='i', attrs={"class": [IconEnum.ACCESS.value]}).render() + f' Allowed Operations for {self.root_metadata}'

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        #table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table

    def get_queryset(self):
        return AllowedOperation.objects.filter(root_metadata=self.root_metadata)
