import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, When
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from MrMap.decorator import check_permission, check_ownership
from MrMap.messages import PUBLISH_REQUEST_ACCEPTED, PUBLISH_REQUEST_DENIED, PUBLISH_PERMISSION_REMOVED, \
    SERVICE_REGISTRATION_ABORTED
from MrMap.responses import DefaultContext
from structure.filters import GroupFilter, OrganizationFilter
from structure.settings import PENDING_REQUEST_TYPE_PUBLISHING
from structure.forms import GroupForm, OrganizationForm, PublisherForOrganizationForm, RemoveGroupForm, \
    RemoveOrganizationForm, AcceptDenyPublishRequestForm, RemovePublisher
from structure.models import MrMapGroup, Permission, Organization, PendingRequest, PendingTask
from structure.models import MrMapUser
from structure.tables import GroupTable, OrganizationTable, PublisherTable, PublisherRequestTable, PublishesForTable
from django.urls import reverse
from users.helper import user_helper
from users.helper.user_helper import create_group_activity


def _prepare_group_table(request: HttpRequest, user: MrMapUser, current_view: str):
    user_groups = user.get_groups().order_by(Case(When(name='Public', then=0)), 'name')
    groups_table = GroupTable(request=request,
                              queryset=user_groups,
                              order_by_field='sg',  # sg = sort groups
                              filter_set_class=GroupFilter,
                              current_view=current_view,
                              param_lead='group-t',
                              )

    return {"groups": groups_table, }


def _prepare_orgs_table(request: HttpRequest, user: MrMapUser, current_view: str):
    all_orgs = Organization.objects.all()

    all_orgs = all_orgs.order_by(
        Case(When(id=user.organization.id if user.organization is not None else 0, then=0), default=1),
        'organization_name')

    all_orgs_table = OrganizationTable(request=request,
                                       queryset=all_orgs,
                                       order_by_field='so',  # sg = sort groups
                                       filter_set_class=OrganizationFilter,
                                       current_view=current_view,
                                       param_lead='orgs-t',)

    return {"organizations": all_orgs_table, }


@login_required
def index(request: HttpRequest, update_params=None, status_code=None):
    """ Renders an overview of all groups and organizations
    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "views/structure_index.html"
    user = user_helper.get_user(request)

    params = {
        "current_view": 'structure:index',
    }
    params.update(_prepare_group_table(request=request, user=user, current_view='structure:index'))
    params.update(_prepare_orgs_table(request=request, user=user, current_view='structure:index'))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
def groups_index(request: HttpRequest, update_params=None, status_code=None):
    """ Renders an overview of all groups

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    template = "views/groups_index.html"
    user = user_helper.get_user(request)

    params = {
        "current_view": "structure:groups-index",
    }
    params.update(_prepare_group_table(request=request, user=user, current_view='structure:groups-index'))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
def organizations_index(request: HttpRequest, update_params=None, status_code=None):
    """ Renders an overview of all organizations

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    template = "views/organizations_index.html"
    user = user_helper.get_user(request)

    params = {
        "current_view": "structure:organizations-index",
    }
    params.update(_prepare_orgs_table(request=request, user=user, current_view='structure:organizations-index'))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
def detail_organizations(request: HttpRequest, object_id: int, update_params=None, status_code=None):
    """ Renders an overview of a group's details.

    Args:
        request: The incoming request
        org_id: The id of the requested group
        update_params:
        status_code:
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)
    org = get_object_or_404(Organization, id=object_id)
    members = MrMapUser.objects.filter(organization=org)
    sub_orgs = Organization.objects.filter(parent=org)
    template = "views/organizations_detail_no_base.html" if 'no-base' in request.GET else "views/organizations_detail.html"

    # list publishers and requests
    pub_requests = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=object_id)
    pub_requests_table = PublisherRequestTable(
        data=pub_requests,
        request=request,
    )

    all_publishing_groups = MrMapGroup.objects.filter(publish_for_organizations__id=object_id)
    publisher_table = PublisherTable(
        data=all_publishing_groups,
        request=request,
    )

    suborganizations = Organization.objects.filter(parent=org)

    params = {
        "organization": org,
        "suborganizations": suborganizations,
        "members": members,
        "sub_organizations": sub_orgs,  # ToDo: nicht in template
        "pub_requests": pub_requests,
        "pub_requests_table": pub_requests_table,
        "all_publisher_table": publisher_table,
        'caption': _("Shows informations about the organization."),
        "current_view": "structure:detail-organization",
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
@check_ownership(MrMapGroup, 'object_id')
def detail_group(request: HttpRequest, object_id: int, update_params=None, status_code=None):
    """ Renders an overview of a group's details.

    Args:
        request: The incoming request
        object_id: The id of the requested group
        update_params:
        status_code:
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)

    group = get_object_or_404(MrMapGroup, id=object_id)
    members = group.user_set.all()
    template = "views/groups_detail_no_base.html" if 'no-base' in request.GET else "views/groups_detail.html"

    publisher_for = group.publish_for_organizations.all()
    all_publisher_table = PublishesForTable(
        data=publisher_for,
        request=request,
    )

    subgroups = MrMapGroup.objects.filter(parent_group=group)

    inherited_permission = []
    parent = group.parent_group
    while parent is not None:
        permissions = user.get_permissions(parent)
        perm_dict = {
            "group": parent,
            "permissions": permissions,
        }
        inherited_permission.append(perm_dict)
        parent = parent.parent_group

    params = {
        "group": group,
        "subgroups": subgroups,
        "inherited_permission": inherited_permission,
        "group_permissions": user.get_permissions(group),
        "members": members,
        "show_registering_for": True,
        "all_publisher_table": all_publisher_table,
        "caption": _("Shows informations about the group."),
        "current_view": "structure:detail-group",
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


def remove_task(request: HttpRequest, task_id: int):
    """ Removes a pending task from the PendingTask table

    Args:
        request (HttpRequest): The incoming request
        task_id (str): The task identifier
    Returns:
        A redirect
    """
    task = get_object_or_404(PendingTask, id=task_id)
    descr = json.loads(task.description)
    messages.info(request, message=SERVICE_REGISTRATION_ABORTED.format(descr.get("service", None)))

    task.delete()
    return redirect(request.META.get("HTTP_REFERER"))


@login_required
@check_permission(Permission(can_edit_organization=True))
@check_ownership(Organization, 'object_id')
def edit_org(request: HttpRequest, object_id: int):
    """ The edit view for changing organization values

    Args:
        request:
        org_id:
    Returns:
         Rendered view
    """
    org = get_object_or_404(Organization, id=object_id)

    form = OrganizationForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:edit-organization',
        reverse_args=[object_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_(f"Edit organization <strong>{org}</strong>"),
        instance=org,)
    return form.process_request(valid_func=form.process_edit_org)


@login_required
@check_permission(Permission(can_delete_organization=True))
@check_ownership(Organization, 'object_id')
def remove_org(request: HttpRequest, object_id: int):
    """ Renders the remove form for an organization

    Args:
        request(HttpRequest): The used request
        org_id: The id of the organization which will be deleted
    Returns:
        A rendered view
    """
    org = get_object_or_404(Organization, id=object_id)
    form = RemoveOrganizationForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:delete-organization',
        reverse_args=[object_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        is_confirmed_label=_("Do you really want to remove this organization?"),
        form_title=_(f"Remove organization <strong>{org}</strong>"),
        instance=org, )
    return form.process_request(valid_func=form.process_remove_org)


@login_required
@check_permission(Permission(can_create_organization=True))
def new_org(request: HttpRequest):
    """ Renders the new organization form and saves the input
    Args:
        request: The incoming request
    Returns:

    """
    form = OrganizationForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:new-organization',
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_(f"Add new organization"), )
    return form.process_request(valid_func=form.process_new_org)


@login_required
@check_permission(Permission(can_toggle_publish_requests=True))
def accept_publish_request(request: HttpRequest, request_id: int):
    """ Activate or decline the publishing request.

    If the request is too old, the publishing will not be accepted.

    Args:
        request (HttpRequest): The incoming request
        request_id (int): The group id
    Returns:
         A View
    """
    user = user_helper.get_user(request)
    # activate or remove publish request/ publisher
    pub_request = get_object_or_404(PendingRequest, type=PENDING_REQUEST_TYPE_PUBLISHING, id=request_id)
    form = AcceptDenyPublishRequestForm(request.POST, pub_request=pub_request)
    if request.method == "POST":
        if form.is_valid():
            if form.cleaned_data['is_accepted']:
                # add organization to group_publisher
                pub_request.group.publish_for_organizations.add(pub_request.organization)
                create_group_activity(
                    group=pub_request.group,
                    user=user,
                    msg=_("Publisher changed"),
                    metadata_title=_("Group '{}' has been accepted as publisher for '{}'".format(pub_request.group,
                                                                                                 pub_request.organization)),
                )
                messages.add_message(request, messages.SUCCESS, PUBLISH_REQUEST_ACCEPTED.format(pub_request.group.name))
            else:
                create_group_activity(
                    group=pub_request.group,
                    user=user,
                    msg=_("Publisher changed"),
                    metadata_title=_("Group '{}' has been rejected as publisher for '{}'".format(pub_request.group,
                                                                                                 pub_request.organization)),
                )
                messages.info(request, PUBLISH_REQUEST_DENIED.format(pub_request.group.name))
            pub_request.delete()
            return HttpResponseRedirect(reverse("structure:detail-organization",
                                                args=(pub_request.organization.id,)),
                                        status=303)
        else:
            for error in form.non_field_errors():
                messages.error(request, error)
            return detail_organizations(request=request, object_id=pub_request.organization.id, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:detail-organization",
                                            args=(pub_request.organization.id,)),
                                    status=303)


@login_required
@check_permission(Permission(can_remove_publisher=True))
@check_ownership(Organization, 'org_id')
@check_ownership(MrMapGroup, 'group_id')
def remove_publisher(request: HttpRequest, org_id: int, group_id: int):
    """ Removes a publisher for an organization

    Args:
        request (HttpRequest): The incoming request
        org_id (int): The organization id
        group_id (int): The group id (publisher)
    Returns:
         A View
    """
    user = user_helper.get_user(request)
    org = get_object_or_404(Organization, id=org_id)
    group = get_object_or_404(MrMapGroup, id=group_id, publish_for_organizations=org)
    if request.method == "POST":
        form = RemovePublisher(request.POST, user=user, organization=org, group=group)
        if form.is_valid():
            group.publish_for_organizations.remove(org)
            create_group_activity(
                group=group,
                user=user,
                msg=_("Publisher changed"),
                metadata_title=_("Group '{}' has been removed as publisher for '{}'.".format(group, org)),
            )
            messages.success(request, message=PUBLISH_PERMISSION_REMOVED.format(group.name, org.organization_name))
            return HttpResponseRedirect(reverse("structure:detail-organization",
                                                args=(org.id,)),
                                        status=303)
        else:
            for error in form.non_field_errors():
                messages.error(request, error)
            return detail_organizations(request=request, org_id=org.id, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:detail-organization",
                                            args=(org.id,)),
                                    status=303)


@login_required
@check_permission(Permission(can_request_to_become_publisher=True))
def publish_request(request: HttpRequest, org_id: int):
    """ Performs creation of a publishing request between a user/group and an organization

    Args:
        request (HttpRequest): The incoming HttpRequest
        org_id (int): The organization id
    Returns:
         A rendered view
    """
    org = get_object_or_404(Organization, id=org_id)

    form = PublisherForOrganizationForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:publish-request',
        reverse_args=[org_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_(f"Request to become publisher for organization <strong>{org}</strong>"),
        organization=org)
    return form.process_request(valid_func=form.process_new_publisher_request)


@login_required
@check_permission(Permission(can_create_group=True))
def new_group(request: HttpRequest):
    """ Renders the new group form and saves the input

    Args:
        request: The incoming request
    Returns:
         A view
    """
    form = GroupForm(data=request.POST or None,
                     request=request,
                     reverse_lookup='structure:new-group',
                     # ToDo: after refactoring of all forms is done, show_modal can be removed
                     show_modal=True,
                     form_title=_(f"Add new group"), )

    return form.process_request(valid_func=form.process_new_group)


@login_required
@check_ownership(MrMapGroup, 'group_id')
def list_publisher_group(request: HttpRequest, group_id: int):
    """ List all organizations a group can publish for

    Args:
        request: The incoming request
        group_id: The group id
    Returns:
        A rendered view
    """
    user = user_helper.get_user(request)

    template = "index_publish_requests.html"
    group = get_object_or_404(MrMapGroup, id=group_id)

    params = {
        "group": group,
        "show_registering_for": True,
    }
    context = DefaultContext(request, params, user).get_context()
    return render(request, template, context)


@login_required
@check_permission(Permission(can_delete_group=True))
@check_ownership(MrMapGroup, 'object_id')
def remove_group(request: HttpRequest, object_id: int):
    """ Renders the remove form for a group

    Args:
        request(HttpRequest): The used request
        object_id:
    Returns:
        A rendered view
    """
    group = get_object_or_404(MrMapGroup, id=object_id)

    form = RemoveGroupForm(data=request.POST or None,
                           request=request,
                           reverse_lookup='structure:delete-group',
                           reverse_args=[object_id, ],
                           # ToDo: after refactoring of all forms is done, show_modal can be removed
                           show_modal=True,
                           is_confirmed_label=_("Do you really want to remove this group?"),
                           form_title=_(f"Remove group <strong>{group}</strong>"),
                           instance=group,)
    return form.process_request(valid_func=form.process_remove_group)


@login_required
@check_permission(Permission(can_edit_group=True))
@check_ownership(MrMapGroup, 'object_id')
def edit_group(request: HttpRequest, object_id: int):
    """ The edit view for changing group values

    Args:
        request:
        group_id:
    Returns:
         A View
    """
    group = get_object_or_404(MrMapGroup, id=object_id)
    form = GroupForm(data=request.POST or None,
                     request=request,
                     reverse_lookup='structure:edit-group',
                     reverse_args=[object_id, ],
                     # ToDo: after refactoring of all forms is done, show_modal can be removed
                     show_modal=True,
                     form_title=_(f"Edit group <strong>{group}</strong>"),
                     instance=group,)
    return form.process_request(valid_func=form.process_edit_group)


def handler404(request: HttpRequest, exception=None):
    """ Handles a general 404 (Page not found) error and renders a custom response page

    Args:
        request: The incoming request
        exception: An exception, if one occured
    Returns:
         A rendered 404 response
    """
    params = {

    }
    context = DefaultContext(request, params)
    response = render(request=request, template_name="404.html", context=context.get_context())
    response.status_code = 404
    return response


def handler500(request: HttpRequest, exception=None):
    """ Handles a general 500 (Internal Server Error) error and renders a custom response page

    Args:
        request: The incoming request
        exception: An exception, if one occured
    Returns:
         A rendered 500 response
    """
    params = {

    }
    context = DefaultContext(request, params)
    response = render(request=request, template_name="500.html", context=context.get_context())
    response.status_code = 500
    return response
