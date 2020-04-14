import datetime
import json
from celery.result import AsyncResult
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from MapSkinner import utils
from MapSkinner.celery_app import app
from MapSkinner.consts import *
from MapSkinner.decorator import check_permission
from MapSkinner.messages import FORM_INPUT_INVALID, GROUP_CAN_NOT_BE_OWN_PARENT, PUBLISH_REQUEST_SENT, \
    PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER, PUBLISH_REQUEST_ABORTED_OWN_ORG, PUBLISH_REQUEST_ABORTED_IS_PENDING, \
    PUBLISH_REQUEST_ACCEPTED, PUBLISH_REQUEST_DENIED, REQUEST_ACTIVATION_TIMEOVER, GROUP_FORM_INVALID, \
    PUBLISH_PERMISSION_REMOVED, ORGANIZATION_CAN_NOT_BE_OWN_PARENT, ORGANIZATION_IS_OTHERS_PROPERTY, \
    GROUP_IS_OTHERS_PROPERTY, PUBLISH_PERMISSION_REMOVING_DENIED, SERVICE_REGISTRATION_ABORTED, \
    ORGANIZATION_SUCCESSFULLY_EDITED, GROUP_SUCCESSFULLY_EDITED, GROUP_SUCCESSFULLY_DELETED, GROUP_SUCCESSFULLY_CREATED
from MapSkinner.responses import BackendAjaxResponse, DefaultContext

from MapSkinner.settings import ROOT_URL
from service.models import Service
from structure.filters import GroupFilter, OrganizationFilter
from structure.settings import PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW, PENDING_REQUEST_TYPE_PUBLISHING
from structure.forms import GroupForm, OrganizationForm, PublisherForOrganizationForm, RemoveGroupForm, RemoveOrganizationForm
from structure.models import MrMapGroup, Role, Permission, Organization, PendingRequest, PendingTask
from structure.models import MrMapUser
from structure.tables import GroupTable, OrganizationTable, PublisherTable, PublisherRequestTable, PublishesForTable
from django.urls import reverse

from users.helper import user_helper
from users.helper.user_helper import create_group_activity


def _prepare_group_table(request: HttpRequest, user: MrMapUser, ):
    user_groups = user.get_groups()
    user_groups_filtered = GroupFilter(request.GET, queryset=user_groups)

    groups = []
    for user_group in user_groups_filtered.qs:
        groups.append(user_group)
        groups.extend(MrMapGroup.objects.filter(
            parent_group=user_group
        ))

    groups_table = GroupTable(groups,
                              order_by_field='sg',  # sg = sort groups
                              user=user, )
    groups_table.filter = user_groups_filtered
    # TODO: since parameters could be changed directly in the uri, we need to make sure to avoid problems
    groups_table.configure_pagination(request, 'groups-t')

    return {"groups": groups_table, }


def _prepare_orgs_table(request: HttpRequest, user: MrMapUser, ):
    all_orgs = Organization.objects.all()

    all_orgs_filtered = OrganizationFilter(request.GET, queryset=all_orgs)

    all_orgs_table = OrganizationTable(all_orgs_filtered.qs,
                                       order_by_field='so',  # so = sort organizations
                                       user=user, )
    all_orgs_table.filter = all_orgs_filtered
    # TODO: since parameters could be changed directly in the uri, we need to make sure to avoid problems
    all_orgs_table.configure_pagination(request, 'orgs-t')

    return {"organizations": all_orgs_table, }


@login_required
def index(request: HttpRequest):
    """ Renders an overview of all groups and organizations
    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "views/structure_index.html"
    user = user_helper.get_user(request)

    group_form = GroupForm()
    organization_form = OrganizationForm()

    params = {
        "new_group_form": group_form,
        "new_organization_form": organization_form,
    }

    params.update(_prepare_group_table(request, user))
    params.update(_prepare_orgs_table(request, user))

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


def remove_task(request: HttpRequest, task_id: int):
    """ Removes a pending task from the PendingTask table

    Args:
        request (HttpRequest): The incoming request
        task_id (str): The task identifier
    Returns:
        A redirect
    """
    task = PendingTask.objects.get(
        id=task_id
    )
    descr = json.loads(task.description)
    messages.info(request, message=SERVICE_REGISTRATION_ABORTED.format(descr.get("service", None)))

    task.delete()
    return redirect(request.META.get("HTTP_REFERER"))


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
    group_form = GroupForm()

    params = {
        "new_group_form": group_form,
    }
    params.update(_prepare_group_table(request, user))

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

    organization_form = OrganizationForm()

    params = {
        "new_organization_form": organization_form,
    }
    params.update(_prepare_orgs_table(request, user))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
def detail_organizations(request: HttpRequest, org_id: int, update_params=None, status_code=None):
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
    org = Organization.objects.get(id=org_id)
    members = MrMapUser.objects.filter(organization=org)
    sub_orgs = Organization.objects.filter(parent=org)
    template = "views/organizations_detail.html"

    # list publishers and requests
    pub_requests = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=org_id)
    pub_requests_table = PublisherRequestTable(
        pub_requests,
        user=user,
    )

    all_publishing_groups = MrMapGroup.objects.filter(publish_for_organizations__id=org_id)
    publisher_table = PublisherTable(
        all_publishing_groups,
        user=user,
    )

    edit_form = OrganizationForm(instance=org, is_edit=True)

    delete_form = RemoveOrganizationForm()
    delete_form.action_url = reverse('structure:delete-organization', args=[org_id])

    publisher_form = PublisherForOrganizationForm()
    publisher_form.fields["organization_name"].initial = org.organization_name
    publisher_form.fields["group"].choices = user.get_groups().values_list('id', 'name')
    publisher_form.action_url = reverse('structure:publish-request', args=[org_id])

    params = {
        "organization": org,
        "members": members,
        "sub_organizations": sub_orgs, # ToDo: nicht in template
        "pub_requests": pub_requests,
        "pub_requests_table": pub_requests_table,
        "all_publisher_table": publisher_table,
        "edit_organization_form": edit_form,
        "delete_organization_form": delete_form,
        "publisher_form": publisher_form,
        'caption': _("Shows informations about the organization which you are selected."),
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
@check_permission(Permission(can_edit_organization=True))
def edit_org(request: HttpRequest, org_id: int):
    """ The edit view for changing organization values

    Args:
        request:
        org_id:
    Returns:
         Rendered view
    """
    user = user_helper.get_user(request)
    org = get_object_or_404(Organization, id=org_id)

    if request.method == "POST":
        form = OrganizationForm(request.POST or None, instance=org, requesting_user=user, is_edit=True)
        if form.is_valid():
            # save changes of group
            form.save()
            messages.success(request, message=ORGANIZATION_SUCCESSFULLY_EDITED.format(org.organization_name))
            return HttpResponseRedirect(reverse("structure:detail-organization", args=(org_id,)), status=303)
        else:
            params = {
                "edit_organization_form": form,
                "show_edit_organization_form": True,
            }
            return detail_organizations(request=request, org_id=org_id, update_params=params, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:detail-organization", args=(org_id,)), status=303)


# TODO: update function documentation
@login_required
@check_permission(Permission(can_delete_organization=True))
def remove_org(request: HttpRequest, org_id: int):
    """ Renders the remove form for an organization

    Args:
        request(HttpRequest): The used request
        org_id:
    Returns:
        A rendered view
    """
    user = user_helper.get_user(request)
    org = get_object_or_404(Organization, id=org_id)

    if request.method == "POST":
        form = RemoveOrganizationForm(request.POST, to_be_deleted_org=org, requesting_user=user)
        if form.is_valid():
            # remove group and all of the related content
            org_name = org.organization_name
            org.delete()
            messages.success(request, message=_('Organization {} successfully deleted.'.format(org_name)))
            return HttpResponseRedirect(reverse("structure:organizations-index"), status=303)
        else:
            params = {
                "delete_organization_form": form,
                "show_delete_organization_form": True,
            }
            return detail_organizations(request=request, org_id=org_id, update_params=params, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:detail-organization", args=(org_id,)), status=303)


@login_required
@check_permission(Permission(can_create_organization=True))
def new_org(request: HttpRequest):
    """ Renders the new organization form and saves the input
    Args:
        request: The incoming request
    Returns:

    """
    user = user_helper.get_user(request)
    form = OrganizationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            org = form.save(commit=False)
            org.created_by = user
            org.is_auto_generated = False  # when the user creates an organization per form, it is not auto generated!
            org.save()
            messages.success(request, message=_('Organization {} successfully created.'.format(org.organization_name)))
            return HttpResponseRedirect(reverse("structure:detail-organization", args=(org.id,)), status=303)
        else:
            params = {
                "new_organization_form": form,
                "show_new_organization_form": True,
            }
            return organizations_index(request=request, update_params=params, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:organizations-index",), status=303)


@login_required
@check_permission(Permission(can_toggle_publish_requests=True))
def accept_publish_request(request: HttpRequest, request_id: int):
    """ Activate or decline the publishing request.

    If the request is too old, the publishing will not be accepted.

    Args:
        request (HttpRequest): The incoming request
        request_id (int): The group id
    Returns:
         A BackendAjaxResponse since it is an Ajax request
    """
    user = user_helper.get_user(request)
    # activate or remove publish request/ publisher
    post_params = request.POST
    is_accepted = utils.resolve_boolean_attribute_val(post_params.get("accept"))
    pub_request = PendingRequest.objects.get(type=PENDING_REQUEST_TYPE_PUBLISHING, id=request_id)
    organization = pub_request.organization
    now = timezone.now()
    if is_accepted and pub_request.activation_until >= now:
        # add organization to group_publisher
        pub_request.group.publish_for_organizations.add(organization)

        create_group_activity(
            group=pub_request.group,
            user=user,
            msg=_("Publisher changed"),
            metadata_title=_("Group '{}' has been accepted as publisher for '{}'".format(pub_request.group, pub_request.organization)),
        )
        messages.add_message(request, messages.SUCCESS, PUBLISH_REQUEST_ACCEPTED.format(pub_request.group.name))
    elif not is_accepted:
        create_group_activity(
            group=pub_request.group,
            user=user,
            msg=_("Publisher changed"),
            metadata_title=_("Group '{}' has been rejected as publisher for '{}'".format(pub_request.group, pub_request.organization)),
        )
        messages.info(request, PUBLISH_REQUEST_DENIED.format(pub_request.group.name))
    elif pub_request.activation_until < now:
        messages.error(request, REQUEST_ACTIVATION_TIMEOVER)
    pub_request.delete()
    return redirect("structure:detail-organization", organization.id)


@login_required
@check_permission(Permission(can_remove_publisher=True))
def remove_publisher(request: HttpRequest, org_id: int, group_id: int):
    """ Removes a publisher for an organization

    Args:
        request (HttpRequest): The incoming request
        org_id (int): The organization id
        group_id (int): The group id (publisher)
    Returns:
         A BackendAjaxResponse since it is an Ajax request
    """
    user = user_helper.get_user(request)

    org = Organization.objects.get(id=org_id)
    group = MrMapGroup.objects.get(id=group_id, publish_for_organizations=org)

    # only allow removing if the user is part of the organization or the group!
    if group not in user.get_groups() and user.organization != org:
        messages.error(request, message=PUBLISH_PERMISSION_REMOVING_DENIED)
    else:
        group.publish_for_organizations.remove(org)
        create_group_activity(
            group=group,
            user=user,
            msg=_("Publisher changed"),
            metadata_title=_("Group '{}' has been removed as publisher for '{}'.".format(group, org)),
        )
        messages.success(request, message=PUBLISH_PERMISSION_REMOVED.format(group.name, org.organization_name))
    return redirect("structure:detail-organization", org.id)


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
    user = user_helper.get_user(request)
    org = Organization.objects.get(id=org_id)
    form = PublisherForOrganizationForm(request.POST, requesting_user=user, organization=org)
    if request.method == 'POST':
        if form.is_valid():
            publish_request_obj = PendingRequest()
            publish_request_obj.type = PENDING_REQUEST_TYPE_PUBLISHING
            publish_request_obj.organization = org
            publish_request_obj.message = form.cleaned_data["request_msg"]
            publish_request_obj.group = form.cleaned_data["group"]
            publish_request_obj.activation_until = timezone.now() + datetime.timedelta(hours=PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW)
            publish_request_obj.save()
            # create pending publish request for organization!
            messages.success(request, message=PUBLISH_REQUEST_SENT)
            return HttpResponseRedirect(reverse("structure:detail-organization", args=(org.id,)), status=303)
        else:
            params = {
                "publisher_form": form,
                "show_publisher_form": True,
            }
            return detail_organizations(request=request, org_id=org_id, update_params=params, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:detail-organization", args=(org_id,)), status=303)


@login_required
def detail_group(request: HttpRequest, group_id: int, update_params=None, status_code=None):
    """ Renders an overview of a group's details.

    Args:
        request: The incoming request
        group_id: The id of the requested group
        update_params:
        status_code:
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)

    group = MrMapGroup.objects.get(id=group_id)
    members = group.user_set.all()
    template = "views/groups_detail.html"

    edit_form = GroupForm(instance=group, is_edit=True)

    delete_form = RemoveGroupForm()
    delete_form.action_url = reverse('structure:delete-group', args=[group_id])

    publisher_for = group.publish_for_organizations.all()
    all_publisher_table = PublishesForTable(
        publisher_for,
        user=user,
    )

    params = {
        "group": group,
        "group_permissions": user.get_permissions(group),
        "members": members,
        "show_registering_for": True,
        "edit_group_form": edit_form,
        "delete_group_form": delete_form,
        "all_publisher_table": all_publisher_table,
        "caption": _("Shows informations about the group which you are selected."),
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
@check_permission(Permission(can_create_group=True))
def new_group(request: HttpRequest):
    """ Renders the new group form and saves the input

    Args:
        request: The incoming request
    Returns:
         A view
    """
    user = user_helper.get_user(request)

    form = GroupForm(request.POST, requesting_user=user)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            group = form.save(commit=False)
            group.created_by = user
            if group.role is None:
                group.role = Role.objects.get(name="_default_")
            group.save()
            group.user_set.add(user)
            messages.success(request, message=GROUP_SUCCESSFULLY_CREATED.format(group.name))
            return HttpResponseRedirect(reverse("structure:detail-group", args=(group.id,)), status=303)
        else:
            params = {
                "new_organization_form": form,
                "show_new_organization_form": True,
            }
        return groups_index(request=request, update_params=params, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:groups-index", ), status=303)


@login_required
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
    group = MrMapGroup.objects.get(id=group_id)

    params = {
        "group": group,
        "show_registering_for": True,
    }
    context = DefaultContext(request, params, user).get_context()
    return render(request, template, context)


# TODO: update function documentation
@login_required
@check_permission(Permission(can_delete_group=True))
def remove_group(request: HttpRequest, group_id: int):
    """ Renders the remove form for a group

    Args:
        request(HttpRequest): The used request
        group_id:
    Returns:
        A rendered view
    """
    user = user_helper.get_user(request)
    group = get_object_or_404(MrMapGroup, id=group_id)
    form = RemoveGroupForm(request.POST, instance=group, requesting_user=user)
    if request.method == "POST":
        if form.is_valid():
            # clean subgroups from parent
            sub_groups = MrMapGroup.objects.filter(
                parent_group=group
            )
            for sub in sub_groups:
                sub.parent = None
                sub.save()
            # remove group and all of the related content
            group.delete()
            messages.success(request, message=GROUP_SUCCESSFULLY_DELETED.format(group.name))
            return HttpResponseRedirect(reverse("structure:groups-index"), status=303)
        else:
            params = {
                "remove_group_form": form,
                "show_remove_group_form": True,
            }
        return detail_group(request=request, group_id=group_id, update_params=params, status_code=422)
    return HttpResponseRedirect(reverse("structure:detail-group", args=(group_id,)), status=303)


@login_required
@check_permission(Permission(can_edit_group=True))
def edit_group(request: HttpRequest, group_id: int):
    """ The edit view for changing group values

    Args:
        request:
        group_id:
    Returns:
         A View
    """
    user = user_helper.get_user(request)
    group = MrMapGroup.objects.get(id=group_id)
    form = GroupForm(request.POST, requesting_user=user, instance=group, is_edit=True)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            group.save()
            messages.success(request, message=GROUP_SUCCESSFULLY_EDITED.format(group.name))
            return HttpResponseRedirect(reverse("structure:detail-group", args=(group.id,)), status=303)
        else:
            params = {
                "edit_group_form": form,
                "show_edit_group_form": True,
            }
        return detail_group(request=request, group_id=group_id, update_params=params, status_code=422)
    else:
        return HttpResponseRedirect(reverse("structure:detail-group", args=(group.id,)), status=303)


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
