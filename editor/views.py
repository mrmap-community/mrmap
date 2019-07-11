from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render, redirect

# Create your views here.
from MapSkinner.decorator import check_session, check_permission
from MapSkinner.responses import DefaultContext
from MapSkinner.settings import ROOT_URL
from editor.forms import MetadataEditorForm
from service.helper.enums import ServiceTypes
from service.models import Metadata, Keyword, Category, ReferenceSystem
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
    wfs_services = user.get_services(ServiceTypes.WFS)
    params = {
        "wfs": wfs_services,
        "wms": wms_services,
    }
    context = DefaultContext(request, params)
    return render(request, template, context.get_context())


@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def edit(request: HttpRequest, id: int, user: User):
    """ The edit view.

    Provides editing functions for the metadata record

    :param request:
    :return:
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
            keywords = editor_form.data.get("keywords").split(",")
            if len(keywords) == 1 and keywords[0] == '':
                keywords = []
            categories = editor_form.data.get("categories").split(",")
            if len(categories) == 1 and categories[0] == '':
                categories = []

            metadata.keywords.clear()
            for kw in keywords:
                keyword = Keyword.objects.get_or_create(keyword=kw)[0]
                metadata.keywords.add(keyword)
            for cat in categories:
                category = Category.objects.get(title_EN=cat)
                metadata.categories.add(category)
            # save metadata
            metadata.is_custom = True
            metadata.save()
            messages.add_message(request, messages.SUCCESS, _("Metadata editing successful"))
            return redirect("editor:index")
        else:
            messages.add_message(request, messages.ERROR, _("The input was not valid."))
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
def restore(request: HttpRequest, id: int, user:User):
    """ Drops custom metadata and load original metadata from capabilities and ISO metadata

    Args,
        request: The incoming request
        id: The metadata id
    Returns:
         Redirects back to edit view
    """
    metadata = Metadata.objects.get(id=id)
    metadata.restore()
    metadata.save()
    messages.add_message(request, messages.INFO, _("Metadata restored to original"))
    return redirect("editor:index")
