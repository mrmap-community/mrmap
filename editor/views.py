from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.shortcuts import render, redirect

# Create your views here.
from MapSkinner.decorator import check_session, check_permission
from MapSkinner.messages import FORM_INPUT_INVALID, METADATA_RESTORING_SUCCESS, METADATA_EDITING_SUCCESS, \
    METADATA_IS_ORIGINAL
from MapSkinner.responses import DefaultContext
from MapSkinner.settings import ROOT_URL
from editor.forms import MetadataEditorForm, FeatureTypeEditorForm
from service.helper.enums import ServiceTypes
from service.models import Metadata, Keyword, Category, ReferenceSystem, FeatureType, Layer
from django.utils.translation import gettext_lazy as _

from structure.models import User, Permission

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

    wms_services = user.get_services(ServiceTypes.WMS)
    wms_layers_custom_md = []
    wms_list = []
    for wms in wms_services:
        child_layers = Layer.objects.filter(parent_service__metadata=wms, metadata__is_custom=True)
        tmp = {
            "root_metadata": wms,
            "custom_subelement_metadata": child_layers,
        }
        wms_list.append(tmp)

    wfs_services = user.get_services(ServiceTypes.WFS)
    wfs_list = []
    for wfs in wfs_services:
        custom_children = FeatureType.objects.filter(service__metadata=wfs, is_custom=True)
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
    editor_form = MetadataEditorForm(request.POST or None)
    editor_form.fields["metadata_url"].required = False
    editor_form.fields["terms_of_use"].required = False
    if request.method == 'POST':
        if editor_form.is_valid():
            custom_md = editor_form.save(commit=False)
            metadata.title = custom_md.title
            metadata.abstract = custom_md.abstract
            metadata.access_constraints = custom_md.access_constraints
            metadata.metadata_url = custom_md.metadata_url
            metadata.terms_of_use = custom_md.terms_of_use

            # get db objects from values
            # keywords are provided as usual text
            keywords = editor_form.data.get("keywords").split(",")
            if len(keywords) == 1 and keywords[0] == '':
                keywords = []
            # categories are provided as id's to prevent language related conflicts
            category_ids = editor_form.data.get("categories").split(",")
            if len(category_ids) == 1 and category_ids[0] == '':
                category_ids = []

            metadata.keywords.clear()
            for kw in keywords:
                keyword = Keyword.objects.get_or_create(keyword=kw)[0]
                metadata.keywords.add(keyword)

            for id in category_ids:
                category = Category.objects.get(id=id)
                metadata.categories.add(category)

            # save metadata
            metadata.is_custom = True
            metadata.save()
            messages.add_message(request, messages.SUCCESS, METADATA_EDITING_SUCCESS)
            return redirect("editor:index")
        else:
            messages.add_message(request, messages.ERROR, FORM_INPUT_INVALID)
            return redirect("editor:edit", id)
    else:
        #metadata = Metadata.objects.get(id=id)
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
        editor_form.fields["metadata_url"].required = False
        editor_form.fields["terms_of_use"].required = False
        params = {
            "service_metadata": metadata,
            "addable_values_list": addable_values_list,
            "form": editor_form,
            "action_url": "{}/editor/edit/{}".format(ROOT_URL, id),
        }
    context = DefaultContext(request, params)
    return render(request, template, context.get_context())

@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def edit_featuretype(request: HttpRequest, id: int, user:User):
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

            # keywords are provided as usual text
            keywords = feature_type_editor_form.data.get("keywords").split(",")
            if len(keywords) == 1 and keywords[0] == '':
                keywords = []

            feature_type.title = custom_ft.title
            feature_type.abstract = custom_ft.abstract

            feature_type.keywords.clear()
            for kw in keywords:
                keyword = Keyword.objects.get_or_create(keyword=kw)[0]
                feature_type.keywords.add(keyword)
            feature_type.is_custom = True
            feature_type.save()
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
                "values": feature_type.keywords.all(),
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
def restore(request: HttpRequest, id: int, user: User):
    """ Drops custom metadata and load original metadata from capabilities and ISO metadata

    Args,
        request: The incoming request
        id: The metadata id
    Returns:
         Redirects back to edit view
    """
    metadata = Metadata.objects.get(id=id)
    if not metadata.is_custom:
        messages.add_message(request, messages.INFO, METADATA_IS_ORIGINAL)
        return redirect(request.META.get("HTTP_REFERER"))
    # identifier = None
    # if not metadata.is_root():
    #     # we need to restore a single layer or feature type
    #     identifier = metadata.service.layer.identifier
    metadata.restore()
    metadata.save()
    messages.add_message(request, messages.INFO, METADATA_RESTORING_SUCCESS)
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
    if not feature_type.is_custom:
        messages.add_message(request, messages.INFO, METADATA_IS_ORIGINAL)
        return redirect(request.META.get("HTTP_REFERER"))
    feature_type.restore()
    feature_type.save()
    messages.add_message(request, messages.INFO, METADATA_RESTORING_SUCCESS)
    return redirect("editor:index")