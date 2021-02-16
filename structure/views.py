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
    PublishesRequestTable, OrganizationDetailTable, PublishersTable, OrganizationMemberTable
from django.urls import reverse_lazy

from users.filters import MrMapUserFilter
from users.helper import user_helper
from django.utils import timezone

from structure.tables import GroupMemberTable


@method_decorator(login_required, name='dispatch')
class GroupTableView(SingleTableMixin, FilterView):
    model = MrMapGroup
    table_class = GroupTable
    filterset_fields = {'name': ['icontains'],
                        'description': ['icontains'],
                        'organization__organization_name': ['icontains']}
    is_public_group = Q(is_public_group=True)
    is_no_permission_group = Q(is_permission_group=False)
    queryset = MrMapGroup.objects.filter(is_no_permission_group | is_public_group).\
        order_by(Case(When(name='Public', then=0)), 'name')

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(GroupTableView, self).get_table(**kwargs)

        table.title = Tag(tag='i', attrs={"class": [IconEnum.GROUP.value]}).render() + _l(' Groups').__str__()

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())))
        table.actions = [render_helper.render_item(item=MrMapGroup.get_add_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self)
        return super(GroupTableView, self).dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class OrganizationTableView(SingleTableMixin, FilterView):
    model = Organization
    table_class = OrganizationTable
    filterset_fields = {'organization_name': ['icontains'],
                        'parent__organization_name': ['icontains'],
                        'is_auto_generated': ['exact']}

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

    def get_initial(self):
        initial = super().get_initial()
        initial.update(self.request.GET.copy())
        return initial

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
class OrganizationMembersTableView(SingleTableMixin, FilterView):
    model = MrMapUser
    table_class = OrganizationMemberTable
    filterset_fields = {'username': ['icontains']}
    template_name = 'structure/views/organizations/members.html'
    object = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.object = get_object_or_404(klass=Organization, pk=kwargs.get('pk'))

    def get_queryset(self):
        return self.object.primary_users.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"object": self.object,
                        'members_count': self.object.primary_users.count(),
                        'publishers_count': self.object.publishers.count(),
                        'publisher_requests_count': PublishRequest.objects.filter(organization=self.object).count()})
        return context

    def get_table_kwargs(self):
        return {'organization': self.object}

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
class OrganizationPublishersTableView(SingleTableMixin, FilterView):
    model = MrMapGroup
    table_class = PublishersTable
    filterset_fields = {'name': ['icontains']}
    template_name = 'structure/views/organizations/publishers.html'
    object = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.object = get_object_or_404(klass=Organization, pk=kwargs.get('pk'))

    def get_queryset(self):
        return self.object.publishers.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"object": self.object,
                        'members_count': self.object.primary_users.count(),
                        'publishers_count': self.object.publishers.count(),
                        'publisher_requests_count': PublishRequest.objects.filter(organization=self.object).count()})
        return context

    def get_table_kwargs(self):
        return {'organization': self.object}

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
class GroupDetailView(DetailView):
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
class GroupMembersTableView(SingleTableMixin, FilterView):
    model = MrMapUser
    table_class = GroupMemberTable
    filterset_fields = {'username': ['icontains'],
                        'organization__organization_name': ['icontains']}
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


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_CREATE_GROUP.value), name='dispatch')
class GroupNewView(SuccessMessageMixin, CreateView):
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
class GroupPublishRightsForTableView(SingleTableMixin, FilterView):
    model = Organization
    table_class = PublishesForTable
    filterset_fields = {'organization_name': ['icontains']}
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


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required(perm=PermissionEnum.CAN_DELETE_GROUP.value), name='dispatch')
@method_decorator(ownership_required(klass=MrMapGroup, id_name='pk'), name='dispatch')
class GroupDeleteView(SuccessMessageMixin, DeleteView):
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
class GroupEditView(SuccessMessageMixin, UpdateView):
    template_name = 'structure/views/generic_form.html'
    success_message = _('Group successfully edited.')
    model = MrMapGroup
    form_class = GroupForm
    queryset = MrMapGroup.objects.filter(is_permission_group=False)

    def get_initial(self):
        initial = super().get_initial()
        initial.update(self.request.GET.copy())
        return initial

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
