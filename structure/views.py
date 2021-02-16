import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Case, When, Q
from django.forms import HiddenInput, MultipleHiddenInput
from django.http import HttpRequest, HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _l
from django.utils.translation import gettext as _
from django.views.generic import DeleteView, DetailView, UpdateView, ListView, CreateView
from django.views.generic.detail import SingleObjectMixin
from django_bootstrap_swt.components import Tag
from django_bootstrap_swt.utils import RenderHelper
from django_filters.views import FilterView
from django_tables2 import SingleTableMixin

from MrMap.decorators import ownership_required, permission_required
from MrMap.icons import IconEnum
from MrMap.messages import RESOURCE_NOT_FOUND_OR_NOT_OWNER, REQUEST_ACTIVATION_TIMEOVER, \
    GROUP_SUCCESSFULLY_DELETED, GROUP_SUCCESSFULLY_CREATED, PUBLISH_REQUEST_DENIED, PUBLISH_REQUEST_ACCEPTED, \
    ORGANIZATION_SUCCESSFULLY_CREATED, ORGANIZATION_SUCCESSFULLY_DELETED
from service.views import default_dispatch, format_html
from structure.filters import GroupFilter, OrganizationFilter
from structure.permissionEnums import PermissionEnum
from structure.forms import GroupForm, OrganizationForm, PublisherForOrganizationForm, \
    RemoveOrganizationForm, RemovePublisherForm, GroupInvitationForm, \
    GroupInvitationConfirmForm, PublishRequestConfirmForm, RemoveUserFromGroupForm
from structure.models import MrMapGroup, Organization, PendingTask, ErrorReport, PublishRequest, GroupInvitationRequest
from structure.models import MrMapUser
from structure.tables import GroupTable, OrganizationTable, PublisherTable, PublishesForTable, GroupDetailTable, \
    PublishesRequestTable, OrganizationDetailTable
from django.urls import reverse_lazy

from users.filters import MrMapUserFilter
from users.helper import user_helper
from django.utils import timezone

from structure.tables import MrMapUserTable


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

    return render(request=request,
                  template_name=template,
                  context=params,
                  status=200 if status_code is None else status_code)


@method_decorator(login_required, name='dispatch')
class MrMapGroupTableView(SingleTableMixin, FilterView):
    model = MrMapGroup
    table_class = GroupTable
    filterset_class = GroupFilter
    is_public_group = Q(is_public_group=True)
    is_no_permission_group = Q(is_permission_group=False)
    queryset = MrMapGroup.objects.filter(is_no_permission_group | is_public_group).\
        order_by(Case(When(name='Public', then=0)), 'name')

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(MrMapGroupTableView, self).get_table(**kwargs)

        table.title = Tag(tag='i', attrs={"class": [IconEnum.GROUP.value]}).render() + _l(' Groups').__str__()

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())))
        table.actions = [render_helper.render_item(item=MrMapGroup.get_add_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self)
        return super(MrMapGroupTableView, self).dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class OrganizationTableView(SingleTableMixin, FilterView):
    model = Organization
    table_class = OrganizationTable
    filterset_fields = ('organization_name', 'parent', 'is_auto_generated')

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by(
            Case(When(id=self.request.user.organization.id if self.request.user.organization is not None else 0, then=0), default=1),
            'organization_name')
        return queryset

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(OrganizationTableView, self).get_table(**kwargs)

        table.title = Tag(tag='i', attrs={"class": [IconEnum.ORGANIZATION.value]}).render() + _l(' Organizations').__str__()

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())))
        table.actions = [render_helper.render_item(item=Organization.get_add_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self)
        return super(OrganizationTableView, self).dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_CREATE_ORGANIZATION.value), name='dispatch')
class OrganizationNewView(SuccessMessageMixin, CreateView):
    model = Organization
    form_class = OrganizationForm
    template_name = 'structure/views/generic_form.html'

    def get_success_message(self, cleaned_data):
        return ORGANIZATION_SUCCESSFULLY_CREATED.format(self.object)

    def get_success_url(self):
        return self.object.detail_view_uri

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('New organization')})
        return context


@method_decorator(login_required, name='dispatch')
class OrganizationDetailView(DetailView):
    class Meta:
        verbose_name = _('Details')

    model = Organization
    template_name = 'structure/views/organizations/details.html'
    queryset = Organization.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Details')})

        details_table = OrganizationDetailTable(data=[self.object, ],
                                                request=self.request)
        context.update({'details_table': details_table,
                        'members_count': self.object.primary_users.count(),
                        'publishers_count': self.object.publishers.count(),
                        'publisher_requests_count': PublishRequest.objects.filter(organization=self.object).count()})
        return context


@method_decorator([login_required,
                   permission_required(perm=PermissionEnum.CAN_EDIT_ORGANIZATION.value,
                                       login_url='structure:organization_overview')],
                  name='dispatch')
class OrganizationEditView(SuccessMessageMixin, UpdateView):
    template_name = 'structure/views/generic_form.html'
    success_message = _('Organization successfully edited.')
    model = Organization
    form_class = OrganizationForm

    def get_success_url(self):
        return self.object.detail_view_uri

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Edit organization')})
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_DELETE_GROUP.value), name='dispatch')
class OrganizationDeleteView(SuccessMessageMixin, DeleteView):
    model = Organization
    template_name = "structure/views/delete.html"
    success_url = reverse_lazy('structure:organization_overview')
    success_message = ORGANIZATION_SUCCESSFULLY_DELETED
    queryset = Organization.objects.filter(is_auto_generated=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Delete organization')})
        return context


@method_decorator(login_required, name='dispatch')
class MrMapGroupDetailView(DetailView):
    class Meta:
        verbose_name = _('Details')

    model = MrMapGroup
    template_name = 'structure/views/groups/details.html'
    queryset = MrMapGroup.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Details')})

        details_table = GroupDetailTable(data=[self.object, ],
                                         request=self.request)
        context.update({'details_table': details_table,
                        'members_count': self.object.user_set.count(),
                        'publishers_count': self.object.publish_for_organizations.count(),
                        'publisher_requests_count': PublishRequest.objects.filter(group=self.object).count()})
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
        context = super().get_context_data(**kwargs)
        context.update({"object": self.object,
                        'members_count': self.object.user_set.count(),
                        'publishers_count': self.object.publish_for_organizations.count(),
                        'publisher_requests_count': PublishRequest.objects.filter(group=self.object).count()})
        return context

    def get_table_kwargs(self):
        return {'group': self.object}

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super().get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Members')
        return table

    def dispatch(self, request, *args, **kwargs):
        # configure table_pagination dynamically to support per_page switching
        self.table_pagination = {"per_page": request.GET.get('per_page', 5), }
        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class PendingTaskDelete(DeleteView):
    model = PendingTask
    success_url = reverse_lazy('resource:index')
    template_name = 'generic_views/generic_confirm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_CREATE_GROUP.value), name='dispatch')
class NewMrMapGroup(SuccessMessageMixin, CreateView):
    model = MrMapGroup
    form_class = GroupForm
    template_name = 'structure/views/generic_form.html'

    def get_success_message(self, cleaned_data):
        return GROUP_SUCCESSFULLY_CREATED.format(self.object)

    def get_success_url(self):
        return self.object.detail_view_uri

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('New group')})
        return context


@method_decorator(login_required, name='dispatch')
class MrMapGroupPublishersTableView(SingleTableMixin, FilterView):
    model = Organization
    table_class = PublishesForTable
    filterset_fields = ('organization__organization_name', )
    template_name = 'structure/views/groups/publishers.html'
    object = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.object = get_object_or_404(klass=MrMapGroup, pk=kwargs.get('pk'))

    def get_queryset(self):
        return self.object.publish_for_organizations.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"object": self.object,
                        'members_count': self.object.user_set.count(),
                        'publishers_count': self.object.publish_for_organizations.count(),
                        'publisher_requests_count': PublishRequest.objects.filter(group=self.object).count()})
        return context

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super().get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}) + _(' Publish for list')
        return table

    def dispatch(self, request, *args, **kwargs):
        # configure table_pagination dynamically to support per_page switching
        self.table_pagination = {"per_page": request.GET.get('per_page', 5), }
        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER.value), name='dispatch')
class PublishRequestNewView(SuccessMessageMixin, CreateView):
    model = PublishRequest
    fields = ('group', 'organization', 'message')
    template_name = 'structure/views/generic_form.html'

    def get_success_message(self, cleaned_data):
        return _('Request was successfully opened')

    def form_valid(self, form):
        group = form.cleaned_data['group']
        organization = form.cleaned_data['organization']
        if group.publish_for_organizations.filter(id=organization.id).exists():
            form.add_error(None, _(f'{group} can already publish for Organization.'))
            return self.form_invalid(form)
        else:
            return super().form_valid(form)

    def get_initial(self):
        initial = super().get_initial()
        initial.update(self.request.GET.copy())
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Publish request')})
        return context


@method_decorator(login_required, name='dispatch')
class PublishRequestTableView(SingleTableMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['group', 'organization', 'message']

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            # show only requests for groups or organization where the user is member of
            # superuser can see all pending requests
            queryset.filter(Q(group__in=self.request.user.get_groups()) |
                            Q(organization=self.request.user.organization))
        return queryset

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super().get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}) + _(' Pending publisher requests')
        return table

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self)
        return super(PublishRequestTableView, self).dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS.value), name='dispatch')
class PublishRequestAcceptView(SuccessMessageMixin, UpdateView):
    model = PublishRequest
    template_name = "structure/views/generic_form.html"
    success_url = reverse_lazy('structure:publish_request_overview')
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED

    def get_initial(self):
        initial = super().get_initial()
        initial.update(self.request.GET)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Accept request')})
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS.value), name='dispatch')
class PublishRequestRemoveView(SuccessMessageMixin, DeleteView):
    model = PublishRequest
    template_name = "structure/views/delete.html"
    success_url = reverse_lazy('structure:index')
    success_message = PUBLISH_REQUEST_DENIED

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Deny request')})
        return context


@method_decorator([login_required,
                   permission_required(perm=PermissionEnum.CAN_REMOVE_USER_FROM_GROUP.value,
                                       login_url='structure:group_overview')],
                  name='dispatch')
class RemoveUserFromGroupView(SuccessMessageMixin, UpdateView):
    template_name = 'structure/views/delete.html'
    success_message = _('Group successfully edited.')
    model = MrMapGroup
    form_class = RemoveUserFromGroupForm
    queryset = MrMapGroup.objects.filter(is_permission_group=False)
    user_who_will_be_removed = None

    def setup(self, request, *args, **kwargs):
        super(RemoveUserFromGroupView, self).setup(request, *args, **kwargs)
        self.user_who_will_be_removed = get_object_or_404(klass=MrMapUser, pk=kwargs.get('user_id'))

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.user_set.count() <= 1:
            # The last user can't be removed from the group
            raise Http404(_("Removing last user from the group isn't possible"))
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.user_who_will_be_removed})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': format_html(_(f'Remove <strong>{self.user_who_will_be_removed}</strong> from <strong>{self.object}</strong>'))})
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_DELETE_GROUP.value), name='dispatch')
@method_decorator(ownership_required(klass=MrMapGroup, id_name='pk'), name='dispatch')
class DeleteMrMapGroupView(SuccessMessageMixin, DeleteView):
    model = MrMapGroup
    template_name = "structure/views/delete.html"
    success_url = reverse_lazy('structure:group_overview')
    success_message = GROUP_SUCCESSFULLY_DELETED
    queryset = MrMapGroup.objects.filter(is_permission_group=False, is_public_group=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Delete group')})
        return context


@method_decorator([login_required,
                   permission_required(perm=PermissionEnum.CAN_EDIT_GROUP.value, login_url='structure:group_overview')],
                  name='dispatch')
class EditGroupView(SuccessMessageMixin, UpdateView):
    template_name = 'structure/views/generic_form.html'
    success_message = _('Group successfully edited.')
    model = MrMapGroup
    form_class = GroupForm
    queryset = MrMapGroup.objects.filter(is_permission_group=False)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': _('Edit group')})
        return context


def handler404(request: HttpRequest, exception=None):
    """ Handles a general 404 (Page not found) error and renders a custom response page

    Args:
        request: The incoming request
        exception: An exception, if one occured
    Returns:
         A rendered 404 response
    """
    response = render(request=request, template_name="404.html")
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
    response = render(request=request, template_name="500.html")
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

    return render(request=request,
                  template_name=template,
                  context=params,
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