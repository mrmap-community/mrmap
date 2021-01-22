from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, When
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.views.generic import DeleteView, DetailView, TemplateView
from django.views.generic.edit import FormMixin, FormView
from django_bootstrap_swt.components import Tag
from django_bootstrap_swt.enums import ButtonColorEnum
from django_filters.views import FilterView
from django_tables2 import SingleTableMixin

from MrMap.decorators import permission_required, ownership_required
from MrMap.icons import IconEnum
from MrMap.messages import SECURITY_PROXY_WARNING_ONLY_FOR_ROOT, METADATA_RESTORING_SUCCESS, SERVICE_MD_RESTORED
from MrMap.responses import DefaultContext
from MrMap.views import GenericUpdateView, ConfirmView, ModelFormView
from editor.filters import EditorAccessFilter
from editor.forms import MetadataEditorForm, RestoreDatasetMetadata, \
    RestrictAccessSpatiallyForm, GeneralAccessSettingsForm
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


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class AccessEditorView(DetailView):
    template_name = "views/editor_edit_access_index.html"
    model = Metadata

    def get_context_data(self, **kwargs):
        context = super(AccessEditorView, self).get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()

        self.request.GET._mutable = True
        self.request.GET.update({'with-base': False})
        self.request.GET._mutable = False

        kwargs.update({"pk": str(self.object.pk)})

        form = GeneralAccessSettingsView.as_view()(request=self.request, **kwargs)
        table = GroupAccessTable.as_view()(request=self.request, **kwargs)

        context.update({"form": form,
                        "table": table})

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class GeneralAccessSettingsView(ModelFormView):
    template_name = "generic_views/generic_form.html"
    form_class = GeneralAccessSettingsForm
    model = Metadata
    no_cataloge_type = ~Q(metadata_type=MetadataEnum.CATALOGUE.value)
    queryset = Metadata.objects.filter(no_cataloge_type)
    action = _("Edit general settings")

    def get_object(self, queryset=None):
        _object = super().get_object(queryset=queryset)
        # currently all settings are only supported for root services
        _object = _object.get_root_metadata()
        self.success_url = _object.detail_view_uri
        self.action_url = reverse("editor:general-access-settings", args=[_object.pk])
        return _object

    # we won't redirect here, cause our js script does not inject the returned form on redirects
    # so we need to overwrite the default form_valid
    def form_valid(self, form):
        form.save()
        return self.render_to_response(self.get_context_data(form=form))


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
class GroupAccessTable(SingleTableMixin, FilterView):
    model = MrMapGroup
    table_class = EditorAcessTable
    filterset_class = EditorAccessFilter
    template_name = "generic_views/generic_list_without_base.html"
    queryset = MrMapGroup.objects.filter(Q(is_permission_group=False) | Q(is_public_group=True)).order_by(Case(
            When(
                is_public_group=True,
                then=0
            )
        ),
        'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        return context

    def get_table_kwargs(self):
        # Next, try looking up by primary key for requested metadata object.
        pk = self.kwargs.get('pk')
        if pk is not None:
            metadata = get_object_or_404(klass=Metadata, id=pk)

        return {
            'related_metadata': metadata
        }

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super().get_table(**kwargs)
        table.title = _('Restrict Access for a group')
        return table


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class RestrictAccessSpatiallyView(ModelFormView):
    template_name = "generic_views/generic_confirm_form.html"
    form_class = RestrictAccessSpatiallyForm
    model = Metadata
    no_cataloge_type = ~Q(metadata_type=MetadataEnum.CATALOGUE.value)
    queryset = Metadata.objects.filter(no_cataloge_type)
    action = "Restrict spatially"
    group = None

    def dispatch(self, request, *args, **kwargs):
        self.group = get_object_or_404(klass=MrMapGroup, id=self.kwargs.get('group_pk', None))
        return super(RestrictAccessSpatiallyView, self).dispatch(request=request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"group": self.group})
        return kwargs

    def get_object(self, queryset=None):
        _object = super().get_object(queryset=queryset)
        self.success_url = _object.detail_view_uri
        self.action_url = reverse("editor:restrict-access-spatially", args=[_object.pk, self.group.id])
        return _object


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(PermissionEnum.CAN_EDIT_METADATA.value), name='dispatch')
@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class RestoreMetadata(ConfirmView):
    model = Metadata
    no_cataloge_type = ~Q(metadata_type=MetadataEnum.CATALOGUE.value)
    is_custom = Q(is_custom=True)
    queryset = Metadata.objects.filter(is_custom | no_cataloge_type)
    action = _("Restore")

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
        messages.add_message(self.request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
        return HttpResponseRedirect(success_url)
