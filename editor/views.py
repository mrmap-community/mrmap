from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, When
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.views.generic import DeleteView
from MrMap.decorators import permission_required, ownership_required
from MrMap.messages import SECURITY_PROXY_WARNING_ONLY_FOR_ROOT, METADATA_RESTORING_SUCCESS, SERVICE_MD_RESTORED
from MrMap.responses import DefaultContext
from MrMap.views import GenericUpdateView
from editor.filters import EditorAccessFilter
from editor.forms import MetadataEditorForm, RestoreDatasetMetadata, \
    RestrictAccessForm, RestrictAccessSpatially
from editor.tables import EditorAcessTable
from service.helper.enums import MetadataEnum, ResourceOriginEnum
from service.models import Metadata
from structure.models import MrMapGroup
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_REMOVE_DATASET_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class DatasetDelete(DeleteView):
    model = Metadata
    success_url = reverse_lazy('resource:index')
    template_name = 'generic_views/generic_confirm.html'
    # todo: filter isn't working as expected. See issue #519
    #  what's about dataset metadatas without any relations?
    queryset = Metadata.objects.filter(metadata_type=MetadataEnum.DATASET.value, related_metadata__origin=ResourceOriginEnum.EDITOR.value)

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
class EditMetadata(GenericUpdateView):
    model = Metadata
    form_class = MetadataEditorForm
    queryset = Metadata.objects.all().exclude(metadata_type=MetadataEnum.CATALOGUE.value)

    def get_object(self, queryset=None):
        instance = super().get_object(queryset=queryset)
        self.action_url = instance.edit_view_uri
        self.action = _("Edit " + instance.__str__())
        return instance


@login_required
@permission_required(PermissionEnum.CAN_EDIT_METADATA.value)
@ownership_required(Metadata, 'object_id')
def edit_access(request: HttpRequest, object_id, update_params: dict = None, status_code: int = 200,):
    """ The edit view for the operations access

    Provides a form to set the access permissions for a metadata-related object.
    Processes the form input afterwards

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         A rendered view
    """
    template = "views/editor_edit_access_index.html"
    user = user_helper.get_user(request)
    md = get_object_or_404(Metadata,
                           ~Q(metadata_type=MetadataEnum.CATALOGUE.value),
                           id=object_id)
    is_root = md.is_root()

    form = RestrictAccessForm(
        data=request.POST or None,
        request=request,
        action_url=reverse('editor:edit_access', args=[object_id, ], ),
        metadata=md
    )

    all_groups = MrMapGroup.objects.filter(
        is_permission_group=False
    )
    all_groups = MrMapGroup.objects.filter(
        is_public_group=True
    ) | all_groups

    all_groups = all_groups.order_by(
        Case(
            When(
                is_public_group=True,
                then=0
            )
        ),
        'name'
    )

    table = EditorAcessTable(
        request=request,
        queryset=all_groups,
        filter_set_class=EditorAccessFilter,
        current_view='editor:edit_access',
        related_metadata=md,
    )

    params = {
        "restrict_access_form": form,
        "restrict_access_table": table,
        "service_metadata": md,
        "is_root": is_root,
    }

    if request.method == 'POST':
        # Check if update form is valid or action is performed on a root metadata
        if not is_root:
            messages.error(request, SECURITY_PROXY_WARNING_ONLY_FOR_ROOT)
        elif form.is_valid():
            form.process_securing_access(md)

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
def access_geometry_form(request: HttpRequest, metadata_id, group_id):
    """ Renders the geometry form for the access editing

    Args:
        request (HttpRequest): The incoming request
        metadata_id (int): The id of the metadata object, which will be edited
        group_id:
    Returns:

    """
    get_object_or_404(Metadata,
                      ~Q(metadata_type=MetadataEnum.CATALOGUE.value),
                      id=metadata_id)
    group = get_object_or_404(MrMapGroup, id=group_id)
    form = RestrictAccessSpatially(
        data=request.POST or None,
        request=request,
        reverse_lookup='editor:access_geometry_form',
        reverse_args=[metadata_id, group_id],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_(f"Edit spatial area for group <strong>{group.name}</strong>"),
        metadata_id=metadata_id,
        group_id=group_id,
    )
    return form.process_request(valid_func=form.process_restict_access_spatially)


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class RestoreMetadata(DeleteView):
    """
    Abuse DeleteView caus of easy confirm post logic here
    """
    model = Metadata
    no_cataloge_type = ~Q(metadata_type=MetadataEnum.CATALOGUE.value)
    no_dataset_type = ~Q(metadata_type=MetadataEnum.DATASET.value)
    is_custom = Q(is_custom=True)
    queryset = Metadata.objects.filter(is_custom | no_cataloge_type | no_dataset_type)
    template_name = 'generic_views/generic_confirm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context.update({
            "action_url": self.object.restore_view_uri,
            "action": _("Restore"),
            "msg": _("Are you sure you want to restore " + self.object.__str__()) + "?"
        })
        return context

    def delete(self, request, *args, **kwargs):
        """

        """
        self.object = self.get_object()

        ext_auth = self.object.get_external_authentication_object()

        self.object.restore(self.object.identifier, external_auth=ext_auth)

        # Todo: add last_changed_by_user field to Metadata and move this piece of code to Metadata.restore()
        user_helper.create_group_activity(self.object.created_by, self.request.user, SERVICE_MD_RESTORED,
                                          "{}: {}".format(self.object.get_parent_service_metadata.title, self.object.title))

        success_url = self.get_success_url()

        messages.add_message(self.request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
        return HttpResponseRedirect(success_url)


@login_required
@permission_required(PermissionEnum.CAN_EDIT_METADATA.value)
@ownership_required(Metadata, 'metadata_id')
def restore_dataset_metadata(request: HttpRequest, metadata_id):
    """ Drops custom metadata and load original metadata from capabilities and ISO metadata

    Args,
        request: The incoming request
        metadata_id: The metadata id
    Returns:
         Redirects back to edit view
    """
    metadata = get_object_or_404(Metadata,
                                 ~Q(metadata_type=MetadataEnum.CATALOGUE.value),
                                 id=metadata_id)

    form = RestoreDatasetMetadata(data=request.POST or None,
                                  request=request,
                                  reverse_lookup='editor:restore-dataset-metadata',
                                  reverse_args=[metadata_id, ],
                                  # ToDo: after refactoring of all forms is done, show_modal can be removed
                                  show_modal=True,
                                  is_confirmed_label=_("Do you really want to restore this dataset?"),
                                  form_title=_(f"Restore dataset metadata <strong>{metadata.title}</strong>"),
                                  instance=metadata)
    return form.process_request(valid_func=form.process_restore_dataset_metadata)
