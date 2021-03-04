from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.db.models import Q
from django.views.generic import DeleteView, DetailView, UpdateView
from django_bootstrap_swt.components import Tag
from django_bootstrap_swt.utils import RenderHelper
from django_filters.views import FilterView
from django_tables2 import SingleTableMixin

from MrMap.decorators import permission_required, ownership_required
from MrMap.forms import get_current_view_args
from MrMap.icons import IconEnum
from MrMap.messages import METADATA_RESTORING_SUCCESS, SERVICE_MD_RESTORED, RESOURCE_EDITED
from MrMap.views import GenericUpdateView, ConfirmView, GenericViewContextMixin, InitFormMixin
from editor.filters import AllowedOperationFilter
from editor.forms import MetadataEditorForm
from editor.tables import AllowedOperationTable
from service.helper.enums import MetadataEnum, ResourceOriginEnum
from service.models import Metadata, AllowedOperation
from service.views import default_dispatch
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_REMOVE_DATASET_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class DatasetDelete(DeleteView):
    model = Metadata
    success_url = reverse_lazy('resource:dataset-index')
    template_name = 'generic_views/generic_confirm.html'

    def get_queryset(self):
        return self.get_object().get_related_dataset_metadatas(filters={'to_metadatas__origin': ResourceOriginEnum.EDITOR.value})

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context.update({
            "action_url": self.object.remove_view_uri,
            "action": _("Delete"),
            "msg": _("Are you sure you want to delete " + self.object.__str__()) + "?"
        })
        return context

    def delete(self, request, *args, **kwargs):
        """
            Creates an async task job which will do the deletion on the fetched object and then redirect to the
            success URL.
        """
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.delete(force=True)
        messages.success(self.request, message=_("Dataset successfully deleted."))
        return HttpResponseRedirect(success_url)


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class EditMetadata(GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, UpdateView):
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = RESOURCE_EDITED
    model = Metadata
    form_class = MetadataEditorForm
    queryset = Metadata.objects.all().exclude(metadata_type=MetadataEnum.CATALOGUE.value)

    def get_title(self):
        return _("Edit " + self.get_object().__str__())


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class RestoreMetadata(GenericViewContextMixin, SuccessMessageMixin, ConfirmView):
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

        # Todo: add last_changed_by_user field to Metadata and move this piece of code to Metadata.restore()
        if self.object.is_metadata_type(MetadataEnum.DATASET):
            user_helper.create_group_activity(self.object.created_by, self.request.user, SERVICE_MD_RESTORED,
                                              "{}".format(self.object.title, ))
        else:
            user_helper.create_group_activity(self.object.created_by, self.request.user, SERVICE_MD_RESTORED,
                                              "{}: {}".format(self.object.get_root_metadata().title,
                                                              self.object.title))

        success_url = self.get_success_url()
        return HttpResponseRedirect(success_url)


@method_decorator(login_required, name='dispatch')
class AllowedOperationTableView(SingleTableMixin, FilterView):
    model = AllowedOperation
    table_class = AllowedOperationTable
    filterset_class = AllowedOperationFilter
    template_name = 'generic_views/generic_list_with_base.html'
    root_metadata = None

    def dispatch(self, request, *args, **kwargs):
        self.root_metadata = get_object_or_404(Metadata, id=kwargs.get('pk', None))
        default_dispatch(instance=self)
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
