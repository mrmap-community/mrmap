import json

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render, redirect

# Create your views here.
from MapSkinner.decorator import check_session, check_permission
from MapSkinner.messages import FORM_INPUT_INVALID, METADATA_RESTORING_SUCCESS, METADATA_EDITING_SUCCESS, \
    METADATA_IS_ORIGINAL, SERVICE_MD_RESTORED, SERVICE_MD_EDITED, NO_PERMISSION, EDITOR_ACCESS_RESTRICTED
from MapSkinner.responses import DefaultContext
from MapSkinner.settings import ROOT_URL
from editor.forms import MetadataEditorForm, FeatureTypeEditorForm
from editor.settings import WMS_SECURED_OPERATIONS, WFS_SECURED_OPERATIONS
from service.helper.enums import ServiceEnum, MetadataEnum
from service.models import Metadata, Keyword, Category, FeatureType, Layer, RequestOperation, SecuredOperation
from django.utils.translation import gettext_lazy as _

from structure.models import User, Permission, Group
from users.helper import user_helper
from editor.helper import editor_helper


@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def index(request: HttpRequest, user:User):
    """ The index view of the editor app.

    Lists all services with information of custom set metadata.

    Args:
        request: The incoming request
    Returns:
    """
    # get all services that are registered by the user
    template = "editor_index.html"

    wms_services = user.get_services(ServiceEnum.WMS)
    wms_layers_custom_md = []
    wms_list = []
    for wms in wms_services:
        child_layers = Layer.objects.filter(parent_service__metadata=wms, metadata__is_custom=True)
        tmp = {
            "root_metadata": wms,
            "custom_subelement_metadata": child_layers,
        }
        wms_list.append(tmp)

    wfs_services = user.get_services(ServiceEnum.WFS)
    wfs_list = []
    for wfs in wfs_services:
        custom_children = FeatureType.objects.filter(service__metadata=wfs, metadata__is_custom=True)
        tmp = {
            "root_metadata": wfs,
            "custom_subelement_metadata": custom_children,
        }
        wfs_list.append(tmp)
    params = {
        "wfs": wfs_list,
        "wms": wms_list,
    }
    context = DefaultContext(request, params)
    return render(request, template, context.get_context())


@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def edit(request: HttpRequest, id: int, user: User):
    """ The edit view for metadata

    Provides editing functions for all elements which are described by Metadata objects

    Args:
        request: The incoming request
        id: The metadata id
        user: The performing user
    Returns:
        A rendered view
    """
    metadata = Metadata.objects.get(id=id)

    # check if user owns this service by group-relation
    if metadata.created_by not in user.groups.all():
        messages.error(request, message=NO_PERMISSION)
        return redirect("editor:index")

    editor_form = MetadataEditorForm(request.POST or None)
    editor_form.fields["terms_of_use"].required = False
    if request.method == 'POST':
        if editor_form.is_valid():

            custom_md = editor_form.save(commit=False)
            if not metadata.is_root():
                # this is for the case that we are working on a non root element which is not allowed to change the
                # inheritance setting for the whole service -> we act like it didn't change
                custom_md.inherit_proxy_uris = metadata.inherit_proxy_uris
            editor_helper.resolve_iso_metadata_links(request, metadata, editor_form)
            editor_helper.overwrite_metadata(metadata, custom_md, editor_form)
            messages.add_message(request, messages.SUCCESS, METADATA_EDITING_SUCCESS)
            _type = metadata.get_service_type()
            if _type == 'wms':
                if metadata.is_root():
                    parent_service = metadata.service
                else:
                    parent_service = metadata.service.parent_service
            elif _type == 'wfs':
                if metadata.is_root():
                    parent_service = metadata.service
                else:
                    parent_service = metadata.featuretype.service

            user_helper.create_group_activity(metadata.created_by, user, SERVICE_MD_EDITED, "{}: {}".format(parent_service.metadata.title, metadata.title))
            return redirect("editor:index")
        else:
            messages.add_message(request, messages.ERROR, FORM_INPUT_INVALID)
            return redirect("editor:edit", id)
    else:
        addable_values_list = [
            {
                "title": _("Keywords"),
                "name": "keywords",
                "values": metadata.keywords.all(),
                "all_values": Keyword.objects.all().order_by("keyword"),
            },
            {
                "title": _("Categories"),
                "name": "categories",
                "values": metadata.categories.all(),
                "all_values": Category.objects.all().order_by("title_EN"),
            },
        ]
        template = "editor_edit.html"
        editor_form = MetadataEditorForm(instance=metadata)
        editor_form.fields["terms_of_use"].required = False
        if not metadata.is_root():
            del editor_form.fields["inherit_proxy_uris"]
        params = {
            "service_metadata": metadata,
            "addable_values_list": addable_values_list,
            "form": editor_form,
            "action_url": "{}/editor/edit/{}".format(ROOT_URL, id),
        }
    context = DefaultContext(request, params)
    return render(request, template, context.get_context())

# ToDo:Remove this function by time, if we can be sure it is safe without!
@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def edit_featuretype(request: HttpRequest, id: int, user: User):
    """ The edit view for FeatureTypes

    Since FeatureTypes do not have describing Metadata, we need to handle them separately

    Args:
        request: The incoming request
        id: The featuretype id
        user: The performing user
    Returns:
         A rendered view
    """
    template = "editor_edit.html"
    feature_type = FeatureType.objects.get(id=id)
    feature_type_editor_form = FeatureTypeEditorForm(request.POST or None)
    feature_type_editor_form.fields["abstract"].required = False
    if request.method == 'POST':
        # save new values to feature type
        if feature_type_editor_form.is_valid():
            custom_ft = feature_type_editor_form.save(False)
            editor_helper.overwrite_featuretype(feature_type, custom_ft, feature_type_editor_form)
            messages.add_message(request, messages.SUCCESS, METADATA_EDITING_SUCCESS)
            return redirect("editor:index")
        else:
            messages.add_message(request, messages.ERROR, FORM_INPUT_INVALID)
            return redirect(request.META.get("HTTP_REFERER"))
    else:
        feature_type_editor_form = FeatureTypeEditorForm(instance=feature_type)
        feature_type_editor_form.fields["abstract"].required = False
        addable_values_list = [
            {
                "title": _("Keywords"),
                "name": "keywords",
                "values": feature_type.metadata.keywords.all(),
                "all_values": Keyword.objects.all().order_by("keyword"),
            }
        ]
        params = {
                "service_metadata": feature_type,
                "addable_values_list": addable_values_list,
                "form": feature_type_editor_form,
                "action_url": "{}/editor/edit/featuretype/{}".format(ROOT_URL, id),}
    context = DefaultContext(request, params).get_context()
    return render(request, template, context)

@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def edit_access(request: HttpRequest, id: int, user: User):
    """ The edit view for the operations access

    Provides a form to set the access permissions for a metadata-related object.
    Processes the form input afterwards

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
        user (User): The performing user
    Returns:
         A rendered view
    """
    md = Metadata.objects.get(id=id)
    md_type = md.metadata_type.type
    template = "editor_edit_access.html"
    post_params = request.POST

    if request.method == "POST":
        # process form input
        editor_helper.process_secure_operations_form(post_params, md)
        messages.success(request, EDITOR_ACCESS_RESTRICTED.format(md.title))
        md.save()
        if md_type == MetadataEnum.FEATURETYPE.value:
            redirect_id = md.featuretype.service.metadata.id
        else:
            if md.service.is_root:
                redirect_id = md.id
            else:
                redirect_id = md.service.parent_service.metadata.id
        return redirect("service:detail", redirect_id)

    else:
        # render form
        metadata_type = md.metadata_type.type
        if metadata_type == MetadataEnum.FEATURETYPE.value:
            _type = ServiceEnum.WFS.value
        else:
            _type = md.service.servicetype.name
        secured_operations = []
        if _type == ServiceEnum.WMS.value:
            secured_operations = WMS_SECURED_OPERATIONS
        elif _type == ServiceEnum.WFS.value:
            secured_operations = WFS_SECURED_OPERATIONS

        operations = RequestOperation.objects.filter(
            operation_name__in=secured_operations
        )
        sec_ops = SecuredOperation.objects.filter(
            secured_metadata=md
        )
        all_groups = Group.objects.all()
        tmp = editor_helper.prepare_secured_operations_groups(operations, sec_ops, all_groups)

        params = {
            "service_metadata": md,
            "operations": tmp,
        }

    context = DefaultContext(request, params).get_context()
    return render(request, template, context)


@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def restore(request: HttpRequest, id: int, user: User):
    """ Drops custom metadata and load original metadata from capabilities and ISO metadata

    Args,
        request: The incoming request
        id: The metadata id
    Returns:
         Redirects back to edit view
    """
    metadata = Metadata.objects.get(id=id)

    # check if user owns this service by group-relation
    if metadata.created_by not in user.groups.all():
        messages.error(request, message=NO_PERMISSION)
        return redirect("editor:index")

    service_type = metadata.get_service_type()
    if service_type == 'wms':
        children_md = Metadata.objects.filter(service__parent_service__metadata=metadata, is_custom=True)
    elif service_type == 'wfs':
        children_md = Metadata.objects.filter(featuretype__service__metadata=metadata, is_custom=True)

    if not metadata.is_custom and len(children_md) == 0:
        messages.add_message(request, messages.INFO, METADATA_IS_ORIGINAL)
        return redirect(request.META.get("HTTP_REFERER"))

    if metadata.is_custom:
        metadata.restore(metadata.identifier)
        metadata.save()

    for md in children_md:
        md.restore(md.identifier)
        md.save()
    messages.add_message(request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
    if not metadata.is_root():
        if service_type == 'wms':
            parent_metadata = metadata.service.parent_service.metadata
        elif service_type == 'wfs':
            parent_metadata = metadata.featuretype.service.metadata
        else:
            # This case is not important now
            pass
    else:
        parent_metadata = metadata
    user_helper.create_group_activity(metadata.created_by, user, SERVICE_MD_RESTORED, "{}: {}".format(parent_metadata.title, metadata.title))
    return redirect("editor:index")


@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def restore_featuretype(request: HttpRequest, id: int, user: User):
    """ Drops custom featuretype data and load original from capabilities and ISO metadata

    Args:
        request: The incoming request
        id: The featuretype id
        user: The performing user
    Returns:
         A rendered view
    """
    feature_type = FeatureType.objects.get(id=id)

    # check if user owns this service by group-relation
    if feature_type.created_by not in user.groups.all():
        messages.error(request, message=NO_PERMISSION)
        return redirect("editor:index")

    if not feature_type.is_custom:
        messages.add_message(request, messages.INFO, METADATA_IS_ORIGINAL)
        return redirect(request.META.get("HTTP_REFERER"))
    feature_type.restore()
    feature_type.save()
    messages.add_message(request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
    return redirect("editor:index")
