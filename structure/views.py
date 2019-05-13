from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from MapSkinner.decorator import check_access
from MapSkinner.responses import BackendAjaxResponse
from structure.forms import GroupForm
from structure.models import User, Group, Role, Permission
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
        "permissions": user_helper.get_permissions(user=user),
        "groups": groups,
    }
    return render(request=request, template_name=template, context=params)


@check_access
def detail_group(request: HttpRequest, id: int, user: User):
    """ Renders an overview of a group's details.

    Args:
        request: The incoming request
        id: The id of the requested group
        user: The user object
    Returns:
         A rendered view
    """
    group = Group.objects.get(id=id)
    members = group.users.all()
    template = "group_detail.html"
    params = {
        "group": group,
        "permissions": user_helper.get_permissions(user=user),
        "group_permissions": user_helper.get_permissions(group=group),
        "members": members
    }
    return render(request=request, template_name=template, context=params)


@check_access
def new(request: HttpRequest, user: User):
    """ Renders the new group form and saves the input

    Args:
        request: The incoming request
        user: The user object
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    if not user_helper.has_permission(user=user, permission_needed=Permission(can_create_group=True)):
        messages.add_message(request, messages.ERROR, _("You do not have permissions for this!"))
        return redirect("structure:index")

    template = "group_form.html"
    form = GroupForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            group = form.save(commit=False)
            if group.parent == group:
                messages.add_message(request=request, level=messages.ERROR, message=_("A group can not be parent to itself!"))
            else:
                group.created_by = user
                group.role = Role.objects.get(name="_default_")
                group.save()
            return redirect("structure:index")
    else:
        params = {
            "form": form,
            "article": _("You are creating a new group."),
            "action_url": "/structure/new/"
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()



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
    """ The edit view for changing group values

    Args:
        request:
        id:
        user:
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    template = "group_form.html"
    group = Group.objects.get(id=id)
    form = GroupForm(request.POST or None, instance=group)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            group = form.save(commit=False)
            if group.parent == group:
                messages.add_message(request=request, level=messages.ERROR, message=_("A group can not be parent to itself!"))
            else:
                group.save()
            return redirect("structure:detail-group", group.id)
    else:
        user_perm = user_helper.get_permissions(user=user)
        if not 'can_change_group_role' in user_perm and form.fields.get('role', None) is not None:
            form.fields.pop('role')
        params = {
            "group": group,
            "form": form,
            "article": _("You are editing the group") + " " + group.name,
            "action_url": "/structure/edit/" + str(group.id)
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()
