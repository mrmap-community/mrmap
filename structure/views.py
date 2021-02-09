import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, When, Q
from django.http import HttpRequest, HttpResponseRedirect, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _l
from django.utils.translation import gettext as _
from django.views.generic import DeleteView, DetailView, UpdateView, ListView
from django.views.generic.detail import SingleObjectMixin
from django_bootstrap_swt.components import Tag
from django_bootstrap_swt.utils import RenderHelper
from django_filters.views import FilterView
from django_tables2 import SingleTableMixin

from MrMap.decorators import ownership_required, permission_required
from MrMap.icons import IconEnum
from MrMap.messages import SERVICE_REGISTRATION_ABORTED, RESOURCE_NOT_FOUND_OR_NOT_OWNER, REQUEST_ACTIVATION_TIMEOVER, \
    GROUP_SUCCESSFULLY_DELETED
from MrMap.responses import DefaultContext
from service.views import default_dispatch
from structure.filters import GroupFilter, OrganizationFilter
from structure.permissionEnums import PermissionEnum
from structure.forms import GroupForm, OrganizationForm, PublisherForOrganizationForm, RemoveGroupForm, \
    RemoveOrganizationForm, RemovePublisherForm, GroupInvitationForm, \
    GroupInvitationConfirmForm, LeaveGroupForm, PublishRequestConfirmForm
from structure.models import MrMapGroup, Organization, PendingTask, ErrorReport, PublishRequest, GroupInvitationRequest
from structure.models import MrMapUser
from structure.tables import GroupTable, OrganizationTable, PublisherTable, PublishesForTable, GroupDetailTable
from django.urls import reverse, reverse_lazy

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


@method_decorator(login_required, name='dispatch')
class MrMapGroupTableView(SingleTableMixin, FilterView):
    model = MrMapGroup
    table_class = GroupTable
    filterset_class = GroupFilter

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(MrMapGroupTableView, self).get_table(**kwargs)

        table.title = Tag(tag='i', attrs={"class": [IconEnum.GROUP.value]}).render() + _l(' Groups').__str__()

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())))
        table.actions = [render_helper.render_item(item=MrMapGroup.get_add_group_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self)
        return super(MrMapGroupTableView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.get_groups().order_by(Case(When(name='Public', then=0)), 'name')




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
        'caption': _l("Shows informations about the organization."),
        "current_view": "structure:detail-organization",
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@method_decorator(login_required, name='dispatch')
#@method_decorator(ownership_required(klass=Metadata, id_name='pk'), name='dispatch')
class MrMapGroupDetailView(DetailView):
    model = MrMapGroup
    template_name = 'structure/views/groups/details.html'
    queryset = MrMapGroup.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Details')})

        details_table = GroupDetailTable(data=[self.object, ],
                                         request=self.request)
        context.update({'details_table': details_table})

        return context


@method_decorator(login_required, name='dispatch')
class MrMapGroupMembersTableView(SingleTableMixin, FilterView):
    model = MrMapUser
    table_class = MrMapUserTable
    filterset_class = MrMapUserFilter
    template_name = 'structure/views/groups/members.html'
    object = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.object = get_object_or_404(klass=MrMapGroup, pk=kwargs.get('pk'))

    def get_queryset(self):
        return self.object.user_set.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context.update({"object": self.object})
        return context

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super().get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Members')
        return table

    def dispatch(self, request, *args, **kwargs):
        # configure table_pagination dynamically to support per_page switching
        self.table_pagination = {"per_page": request.GET.get('per_page', 5), }
        self.extra_context = DefaultContext(request=request, context={}).get_context()
        return super().dispatch(request, *args, **kwargs)


@login_required
@ownership_required(MrMapGroup, 'object_id')
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
        "caption": _l("Shows informations about the group."),
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


@method_decorator(login_required, name='dispatch')
class PendingTaskDelete(DeleteView):
    model = PendingTask
    success_url = reverse_lazy('resource:index')
    template_name = 'generic_views/generic_confirm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context.update({
            "action_url": self.object.remove_view_uri,
            "action": _l("Delete"),
            "msg": _l("Are you sure you want to delete " + self.object.__str__()) + "?"
        })
        return context

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
@permission_required(PermissionEnum.CAN_EDIT_ORGANIZATION.value)
@ownership_required(Organization, 'object_id')
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
        form_title=_l(f"Edit organization <strong>{org}</strong>"),
        instance=org,)
    return form.process_request(valid_func=form.process_edit_org)


@login_required
@permission_required(PermissionEnum.CAN_DELETE_ORGANIZATION.value)
@ownership_required(Organization, 'object_id')
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
        is_confirmed_label=_l("Do you really want to remove this organization?"),
        form_title=_l(f"Remove organization <strong>{org}</strong>"),
        instance=org, )
    return form.process_request(valid_func=form.process_remove_org)


@login_required
@permission_required(PermissionEnum.CAN_CREATE_ORGANIZATION.value)
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
        form_title=_l(f"Add new organization"), )
    return form.process_request(valid_func=form.process_new_org)


@login_required
@permission_required(PermissionEnum.CAN_REMOVE_PUBLISHER.value)
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
        is_confirmed_label=_l("Do you really want to remove this publisher?"),
        form_title=_l("Remove publisher <strong>{}</strong>").format(group.name),
        organization=org,
        user=user,
        group=group,
    )
    return form.process_request(valid_func=form.process_remove_publisher)


@login_required
@permission_required(PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER.value)
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
        form_title=_l(f"Request to become publisher for organization <strong>{org}</strong>"),
        organization=org)
    return form.process_request(valid_func=form.process_new_publisher_request)


@login_required
@permission_required(PermissionEnum.CAN_CREATE_GROUP.value)
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
                     form_title=_l(f"Add new group"), )

    return form.process_request(valid_func=form.process_new_group)


@login_required
@ownership_required(MrMapGroup, 'group_id')
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
@permission_required(PermissionEnum.CAN_REMOVE_USER_FROM_GROUP.value)
@ownership_required(MrMapGroup, 'object_id')
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
            _l("The group creator can not be removed!")
        )
    else:
        group.user_set.remove(user)
        messages.success(
            request,
            _l("{} removed from {}").format(user.username, group.name)
        )
    return redirect("structure:detail-group", object_id)


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_DELETE_GROUP.value), name='dispatch')
@method_decorator(ownership_required(klass=MrMapGroup, id_name='pk'), name='dispatch')
class DeleteMrMapGroupView(SuccessMessageMixin, DeleteView):
    model = MrMapGroup
    template_name = "structure/views/groups/delete.html"
    success_url = reverse_lazy('structure:index')
    success_message = GROUP_SUCCESSFULLY_DELETED
    queryset = MrMapGroup.objects.filter(is_permission_group=False, is_public_group=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Delete group')})
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_EDIT_GROUP.value), name='dispatch')
@method_decorator(ownership_required(klass=MrMapGroup, id_name='pk'), name='dispatch')
class EditGroupView(SuccessMessageMixin, UpdateView):
    template_name = 'structure/views/groups/edit.html'
    success_message = _('Group successfully edited.')
    model = MrMapGroup
    form_class = GroupForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Edit group')})
        return context


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
        is_confirmed_label=_l("Do you really want to leave this group?"),
        form_title=_l("Leave group <strong>{}</strong>").format(group),
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
@permission_required(PermissionEnum.CAN_ADD_USER_TO_GROUP.value)
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
        form_title=_l("Invite <strong>{}</strong> to a group.".format(invited_user)),
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
        form_title=_l("{} invites you to group {}.").format(
            invitation.created_by,
            invitation.to_group
        ),
        invitation=invitation,
    )
    return form.process_request(valid_func=form.process_invitation_group)


@login_required
@permission_required(PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS.value)
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
        form_title=_l("{} wants to publish for {}.").format(
            pub_request.group,
            pub_request.organization
        ),
        publish_request=pub_request,
    )
    return form.process_request(valid_func=form.process_publish_request)