import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, When
from django.http import HttpRequest, HttpResponseRedirect, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from MrMap.decorator import check_permission, check_ownership
from MrMap.messages import SERVICE_REGISTRATION_ABORTED, RESOURCE_NOT_FOUND_OR_NOT_OWNER, REQUEST_ACTIVATION_TIMEOVER
from MrMap.responses import DefaultContext
from structure.filters import GroupFilter, OrganizationFilter
from structure.permissionEnums import PermissionEnum
from structure.forms import GroupForm, OrganizationForm, PublisherForOrganizationForm, RemoveGroupForm, \
    RemoveOrganizationForm, RemovePublisherForm, GroupInvitationForm, \
    GroupInvitationConfirmForm, LeaveGroupForm, PublishRequestConfirmForm
from structure.models import MrMapGroup, Organization, PendingTask, ErrorReport, PublishRequest, GroupInvitationRequest
from structure.models import MrMapUser
from structure.tables import GroupTable, OrganizationTable, PublisherTable, PublishesForTable
from django.urls import reverse

from users.filters import MrMapUserFilter
from users.helper import user_helper
from django.utils import timezone

from users.tables import MrMapUserTable


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


def _prepare_users_table(request: HttpRequest, current_view: str, group: MrMapGroup = None):
    """ Prepares user table.

    By default the user table is empty to prevent the reveal of all registered users. Users can only be shown if
    the Search field is used.

    Args:
        request (HttpRequest):
        user (MrMapUser):
        current_view (str):
    Returns:
         dict
    """
    all_users = MrMapUser.objects.none() if group is None else group.user_set.all()

    all_users_table = MrMapUserTable(
        request=request,
        queryset=all_users,
        order_by_field='us',
        filter_set_class=MrMapUserFilter,
        current_view=current_view,
        param_lead='users-t',
        group=group,
    )

    return {"users": all_users_table, }


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
    params.update(_prepare_users_table(request=request, group=None, current_view='structure:index'))

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

    all_publishing_groups = MrMapGroup.objects.filter(publish_for_organizations__id=object_id)
    publisher_table = PublisherTable(
        data=all_publishing_groups,
        request=request,
        organization=org,
        current_view="structure:detail-organization",
    )

    suborganizations = Organization.objects.filter(parent=org)

    params = {
        "organization": org,
        "suborganizations": suborganizations,
        "members": members,
        "sub_organizations": sub_orgs,  # ToDo: nicht in template
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
        "show_registering_for": True,
        "all_publisher_table": all_publisher_table,
        "caption": _("Shows informations about the group."),
        "current_view": "structure:detail-group",
    }
    params.update(
        _prepare_users_table(request=request, group=group, current_view='structure:detail-group')
    )

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)

@login_required
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
    return HttpResponseRedirect(reverse("resource:index"), status=303)


@login_required
def generate_error_report(request: HttpRequest, report_id: int):
    """ Provides the error report as txt download.

    TXT is the only provided file type.

    Args:
        request (HttpRequest):
        report_id:
    Returns:

    """
    TXT = "text/plain"
    error_report = get_object_or_404(ErrorReport, id=report_id)
    data = error_report.generate_report()

    # Create empty response object and fill it with dynamic csv content
    timestamp_now = timezone.now()
    response = HttpResponse(data, content_type=TXT)

    response['Content-Disposition'] = f'attachment; filename="MrMap_error_report_{timestamp_now.strftime("%Y-%m-%dT%H:%M:%S")}.txt"'
    return response


@login_required
@check_permission(PermissionEnum.CAN_EDIT_ORGANIZATION)
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
@check_permission(
    PermissionEnum.CAN_DELETE_ORGANIZATION
)
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
@check_permission(
    PermissionEnum.CAN_CREATE_ORGANIZATION
)
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
@check_permission(
    PermissionEnum.CAN_REMOVE_PUBLISHER
)
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

    form = RemovePublisherForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:remove-publisher',
        reverse_args=[org_id, group_id],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        is_confirmed_label=_("Do you really want to remove this publisher?"),
        form_title=_("Remove publisher <strong>{}</strong>").format(group.name),
        organization=org,
        user=user,
        group=group,
    )
    return form.process_request(valid_func=form.process_remove_publisher)


@login_required
@check_permission(
    PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER
)
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
@check_permission(
    PermissionEnum.CAN_CREATE_GROUP
)
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
@check_permission(
    PermissionEnum.CAN_REMOVE_USER_FROM_GROUP
)
@check_ownership(MrMapGroup, 'object_id')
def remove_user_from_group(request: HttpRequest, object_id: str, user_id: str):
    """ Removes a user from a group

    Args:
        request: The incoming request
        object_id: The group id
        user_id: The user id
    Returns:
         A redirect
    """
    group = get_object_or_404(MrMapGroup, id=object_id)
    user = get_object_or_404(MrMapUser, id=user_id)

    if group.created_by == user:
        messages.error(
            request,
            _("The group creator can not be removed!")
        )
    else:
        group.user_set.remove(user)
        messages.success(
            request,
            _("{} removed from {}").format(user.username, group.name)
        )
    return redirect("structure:detail-group", object_id)


@login_required
@check_permission(
    PermissionEnum.CAN_DELETE_GROUP
)
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

    if group.is_permission_group or group.is_public_group:
        messages.error(
            request,
            _("Group {} is an important main group and therefore can not be removed.").format(_(group.name)),
        )
        return redirect("structure:index")

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
@check_permission(
    PermissionEnum.CAN_EDIT_GROUP
)
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


@login_required
def leave_group(request: HttpRequest, object_id: str):
    """ Removes a user from a group

    Args:
        request: The incoming request
        object_id: The id of the group
    Returns:
         A redirect
    """
    group = get_object_or_404(MrMapGroup, id=object_id)
    form = LeaveGroupForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:leave-group',
        reverse_args=[object_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        is_confirmed_label=_("Do you really want to leave this group?"),
        form_title=_("Leave group <strong>{}</strong>").format(group),
        instance=group,
    )
    return form.process_request(valid_func=form.process_leave_group)


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


def users_index(request: HttpRequest, update_params=None, status_code=None):
    """ Renders an overview of all organizations

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    template = "views/users_index.html"
    user = user_helper.get_user(request)

    params = {
        "current_view": "structure:users-index",
    }
    params.update(_prepare_users_table(request=request, group=None, current_view='structure:users-index'))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
@check_permission(
    PermissionEnum.CAN_ADD_USER_TO_GROUP
)
def user_group_invitation(request: HttpRequest, object_id: str, update_params=None, status_code=None):
    """ Renders and process a form for user-group invitation

    Args:
        request (HttpRequest): The incoming request
        object_id (HttpRequest): The user id for the invited user
    Returns:
         A rendered view
    """
    invited_user = get_object_or_404(MrMapUser, id=object_id)
    form = GroupInvitationForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:invite-user-to-group',
        reverse_args=[object_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_("Invite <strong>{}</strong> to a group.".format(invited_user)),
        invited_user=invited_user,
    )
    return form.process_request(valid_func=form.process_invitation_group)


@login_required
def toggle_group_invitation(request: HttpRequest, object_id: str, update_params=None, status_code=None):
    """ Renders and processes a form to accepting/declining an invitation

    Args:
        request (HttpRequest): The incoming request
        object_id (HttpRequest): The user id for the invited user
    Returns:
         A rendered view
    """
    invitation = get_object_or_404(GroupInvitationRequest, id=object_id)
    form = GroupInvitationConfirmForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:toggle-user-to-group',
        reverse_args=[object_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_("{} invites you to group {}.").format(
            invitation.created_by,
            invitation.to_group
        ),
        invitation=invitation,
    )
    return form.process_request(valid_func=form.process_invitation_group)


@login_required
@check_permission(
    PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS
)
def toggle_publish_request(request: HttpRequest, object_id: str, update_params=None, status_code=None):
    """ Renders and processes a form to accepting/declining an invitation

    Args:
        request (HttpRequest): The incoming request
        object_id (HttpRequest): The user id for the invited user
    Returns:
         A rendered view
    """
    try:
        pub_request = PublishRequest.objects.get(id=object_id)
        now = timezone.now()
        if pub_request.activation_until <= now:
            messages.error(request, REQUEST_ACTIVATION_TIMEOVER)
            pub_request.delete()
            return redirect("home")
    except ObjectDoesNotExist:
        messages.error(request, RESOURCE_NOT_FOUND_OR_NOT_OWNER)
        return redirect("home")

    form = PublishRequestConfirmForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='structure:toggle-publish-request',
        reverse_args=[object_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_("{} wants to publish for {}.").format(
            pub_request.group,
            pub_request.organization
        ),
        publish_request=pub_request,
    )
    return form.process_request(valid_func=form.process_publish_request)