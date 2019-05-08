
from django.http import HttpRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from MapSkinner.decorator import check_access
from MapSkinner.responses import BackendAjaxResponse
from structure.forms import GroupForm
from structure.models import User, Group
from .helper import user_helper


@check_access
def index(request: HttpRequest, user: User):
    """ Renders an overview of all groups

    Args:
        request (HttpRequest): The incoming request
        user (User):
    Returns:
         A view
    """
    template = "index_structure.html"
    user_groups = user.groups.all()
    groups = []
    for user_group in user_groups:
        groups.append(user_group)
        groups.extend(Group.objects.filter(
            parent=user_group
        ))
    params = {
        "permissions": user_helper.get_permissions(user),
        "groups": groups,
    }
    return render(request=request, template_name=template, context=params)


@check_access
def detail_group(request: HttpRequest, id: int, user: User):
    group = Group.objects.get(id=id)
    members = group.users.all()
    template = "group_detail.html"
    params = {
        "group": group,
        "permissions": user_helper.get_permissions(group=group),
        "members": members
    }
    return render(request=request, template_name=template, context=params)


@check_access
def remove(request: HttpRequest, user: User):
    """ Renders the remove form for a service

    Args:
        request(HttpRequest): The used request
    Returns:
        A rendered view
    """
    template = "remove_group_confirmation.html"
    service_id = request.GET.dict().get("id")
    confirmed = request.GET.dict().get("confirmed")
    group = get_object_or_404(Group, id=service_id)
    permission = group.role.permission
    if confirmed == 'false':
        params = {
            "group": group,
            "permissions": permission,
        }
        html = render_to_string(template_name=template, context=params, request=request)
        return BackendAjaxResponse(html=html).get_response()
    else:
        # remove group and all of the related content
        group.delete()
        return BackendAjaxResponse(html="", redirect="/structure").get_response()


@check_access
def edit(request: HttpRequest,id: int, user: User):
    template = "edit_group_form.html"
    group = Group.objects.get(id=id)
    form = GroupForm(request.POST or None, instance=group)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            group = form.save()
            return redirect("structure:detail-group", group.id)
    else:
        params = {
            "group": group,
            "form": form,
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()
