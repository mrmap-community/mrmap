import datetime
import json

from celery.result import AsyncResult
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from MapSkinner import utils
from MapSkinner.celery_app import app
from MapSkinner.decorator import check_session, check_permission
from MapSkinner.messages import FORM_INPUT_INVALID, NO_PERMISSION, GROUP_CAN_NOT_BE_OWN_PARENT, PUBLISH_REQUEST_SENT, \
    PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER, PUBLISH_REQUEST_ABORTED_OWN_ORG, PUBLISH_REQUEST_ABORTED_IS_PENDING, \
    PUBLISH_REQUEST_ACCEPTED, PUBLISH_REQUEST_DENIED, REQUEST_ACTIVATION_TIMEOVER, GROUP_FORM_INVALID, \
    PUBLISH_PERMISSION_REMOVED, ORGANIZATION_CAN_NOT_BE_OWN_PARENT, ORGANIZATION_IS_OTHERS_PROPERTY, \
    GROUP_IS_OTHERS_PROPERTY, PUBLISH_PERMISSION_REMOVING_DENIED, SERVICE_REGISTRATION_ABORTED
from MapSkinner.responses import BackendAjaxResponse, DefaultContext
from MapSkinner.settings import ROOT_URL
from service.models import Service
from structure.settings import PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW, PENDING_REQUEST_TYPE_PUBLISHING
from structure.forms import GroupForm, OrganizationForm, PublisherForOrganization
from structure.models import Group, Role, Permission, Organization, PendingRequest, PendingTask
from structure.models import User


@check_session
def index(request: HttpRequest, user: User):
    """ Renders an overview of all groups and organizations

    Args:
        request (HttpRequest): The incoming request
        user (User): The current user
    Returns:
         A view
    """
    template = "index_structure.html"
    user_groups = user.groups.all()
    all_orgs = Organization.objects.all().order_by('organization_name')
    user_orgs = {
        "primary": user.organization,
    }
    groups = []
    for user_group in user_groups:
        groups.append(user_group)
        groups.extend(Group.objects.filter(
            parent=user_group
        ))
    # check for notifications like publishing requests
    # publish requests
    pub_requests_count = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=user.organization).count()

    params = {
        "groups": groups,
        "all_organizations": all_orgs,
        "user_organizations": user_orgs,
        "pub_requests_count": pub_requests_count,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


def task(request: HttpRequest, id: str):
    """ Returns information about the pending task

    Args:
        request:
        id (str): The task id
    Returns:
         An ajax view
    """
    params = {
        "description": "",
        "id": "",
        "state": "",
        "info": "",
    }
    try:
        task = AsyncResult(id, app=app)
        params.update({
            "id": task.id,
            "state": task.state,
            "info": task.info,
        })
    except AttributeError:
        pass
    try:
        task_db = PendingTask.objects.get(task_id=id)
        desc = json.loads(task_db.description)
        if desc.get("status", None) is None and desc.get("exception", None) is not None:
            # something went wrong, the task has failed!
            tmp = {
                "phase": "Aborted ({})".format(desc.get("exception")),
                "service": desc.get("service", None),
                "exception": desc.get("exception")
            }
            params["info"] = {
                "current": 0,
            }
            task_db.description = json.dumps(tmp)
            task_db.save()
        params["description"] = task_db.description
    except ObjectDoesNotExist:
        # this happens if the db record already was deleted
        # just fake the progress as it would be finished!
        params["info"] = {
            "current": 100,
        }
        params["description"] = json.dumps({
            "service": "",
            "phase": "finished",
        })
    return BackendAjaxResponse(html="", task=params).get_response()


def remove_task(request: HttpRequest, id: str):
    """ Removes a pending task from the PendingTask table

    Args:
        request (HttpRequest): The incoming request
        id (str): The task identifier
    Returns:
        A redirect
    """
    task = PendingTask.objects.get(
        task_id=id
    )
    descr = json.loads(task.description)
    messages.info(request, message=SERVICE_REGISTRATION_ABORTED.format(descr.get("service", None)))

    task.delete()
    return redirect(request.META.get("HTTP_REFERER"))


@check_session
def groups(request: HttpRequest, user: User):
    """ Renders an overview of all groups

    Args:
        request (HttpRequest): The incoming request
        user (User): The current user
    Returns:
         A view
    """
    template = "index_groups_extends.html"
    user_groups = user.groups.all()
    groups = []
    for user_group in user_groups:
        groups.append(user_group)
        groups.extend(Group.objects.filter(
            parent=user_group
        ))
    params = {
        "groups": groups,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
def organizations(request: HttpRequest, user: User):
    """ Renders an overview of all organizations

    Args:
        request (HttpRequest): The incoming request
        user (User): The current user
    Returns:
         A view
    """
    template = "index_organizations_extended.html"
    all_orgs = Organization.objects.all()
    # check for notifications like publishing requests
    # publish requests
    pub_requests_count = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=user.organization).count()
    orgs = {
        "primary": user.organization,
    }
    params = {
        "user_organizations": orgs,
        "all_organizations": all_orgs,
        "pub_requests_count": pub_requests_count,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())

@check_session
def detail_organizations(request:HttpRequest, id: int, user:User):
    """ Renders an overview of a group's details.

    Args:
        request: The incoming request
        id: The id of the requested group
        user: The user object
    Returns:
         A rendered view
    """
    org = Organization.objects.get(id=id)
    members = User.objects.filter(organization=org)
    sub_orgs = Organization.objects.filter(parent=org)
    services = Service.objects.filter(metadata__contact=org, is_root=True)
    template = "organization_detail.html"

    # list publishers
    pub_requests = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=id)
    all_publishing_groups = Group.objects.filter(publish_for_organizations__id=id)
    pub_requests_count = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=user.organization).count()

    params = {
        "organization": org,
        "members": members,
        "sub_organizations": sub_orgs,
        "services": services,
        "pub_requests": pub_requests,
        "all_publisher": all_publishing_groups,
        "pub_requests_count": pub_requests_count,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
@check_permission(Permission(can_edit_organization=True))
def edit_org(request: HttpRequest, id: int, user: User):
    """ The edit view for changing organization values

    Args:
        request:
        id:
        user:
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    template = "form.html"
    org = Organization.objects.get(id=id)
    if org.created_by != user:
        messages.error(request, message=ORGANIZATION_IS_OTHERS_PROPERTY)
        return redirect("structure:detail-organization", org.id)
    form = OrganizationForm(request.POST or None, instance=org)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            org = form.save(commit=False)
            if org.parent == org:
                messages.add_message(request=request, level=messages.ERROR, message=ORGANIZATION_CAN_NOT_BE_OWN_PARENT)
            else:
                org.save()
        return redirect("structure:detail-organization", org.id)

    else:
        params = {
            "organization": org,
            "form": form,
            "article": _("You are editing the organization") + " " + org.organization_name,
            "action_url": ROOT_URL + "/structure/organizations/edit/" + str(org.id)
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()


@check_session
@check_permission(Permission(can_delete_organization=True))
def remove_org(request: HttpRequest, user: User):
    """ Renders the remove form for an organization

    Args:
        request(HttpRequest): The used request
    Returns:
        A rendered view
    """
    template = "remove_organization_confirmation.html"
    _id = request.GET.dict().get("id")
    confirmed = utils.resolve_boolean_attribute_val(request.GET.dict().get("confirmed"))
    org = get_object_or_404(Organization, id=_id)
    if org.created_by != user:
        messages.error(request, message=ORGANIZATION_IS_OTHERS_PROPERTY)
        return redirect("structure:detail-organization", org.id)
    if not confirmed:
        params = {
            "organization": org,
        }
        html = render_to_string(template_name=template, context=params, request=request)
        return BackendAjaxResponse(html=html).get_response()
    else:
        # remove group and all of the related content
        org.delete()
        return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure").get_response()


@check_session
@check_permission(Permission(can_create_organization=True))
def new_org(request: HttpRequest, user: User):
    """ Renders the new organization form and saves the input

    Args:
        request: The incoming request
        user: The user object
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    if not user.has_permission(permission_needed=Permission(can_create_organization=True)):
        messages.add_message(request, messages.ERROR, NO_PERMISSION)
        return redirect("structure:index")

    orgs = list(Organization.objects.values_list("organization_name", flat=True))
    if None in orgs:
        orgs.pop(orgs.index(None))
    template = "form.html"
    form = OrganizationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            org = form.save(commit=False)
            if org.parent == org:
                messages.add_message(request=request, level=messages.ERROR, message=GROUP_CAN_NOT_BE_OWN_PARENT)
            else:
                org.created_by = user
                org.is_auto_generated = False  # when the user creates an organization per form, it is not auto generated!
                org.save()
        else:
            messages.error(request, message=GROUP_FORM_INVALID)
        return redirect("structure:index")
    else:
        params = {
            "organizations": orgs,
            "form": form,
            "article": _("You are creating a new organization. Please make sure the organization does not exist yet to avoid duplicates! You can see if a similar named organization already exists by typing the organization name in the related field."),
            "action_url": ROOT_URL + "/structure/organizations/new/register-form/"
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()


@check_session
@check_permission(Permission(can_toggle_publish_requests=True))
def toggle_publish_request(request: HttpRequest, id: int, user: User):
    """ Activate or decline the publishing request.

    If the request is too old, the publishing will not be accepted.

    Args:
        request (HttpRequest): The incoming request
        id (int): The organization's id
        user (User): The current user object
    Returns:
         A BackendAjaxResponse since it is an Ajax request
    """
    # activate or remove publish request/ publisher
    post_params = request.POST
    is_accepted = utils.resolve_boolean_attribute_val(post_params.get("accept"))
    organization = Organization.objects.get(id=id)
    pub_request = PendingRequest.objects.get(type=PENDING_REQUEST_TYPE_PUBLISHING, id=post_params.get("requestId"))
    now = timezone.now()
    if is_accepted and pub_request.activation_until >= now:
        # add organization to group_publisher
        pub_request.group.publish_for_organizations.add(organization)
        messages.add_message(request, messages.SUCCESS, PUBLISH_REQUEST_ACCEPTED.format(pub_request.group.name))
    elif not is_accepted:
        messages.add_message(request, messages.SUCCESS, PUBLISH_REQUEST_DENIED.format(pub_request.group.name))
    elif pub_request.activation_until < now:
        messages.add_message(request, messages.ERROR, REQUEST_ACTIVATION_TIMEOVER)
    pub_request.delete()
    return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure/organizations/detail/" + str(organization.id)).get_response()


@check_session
@check_permission(Permission(can_remove_publisher=True))
def remove_publisher(request: HttpRequest, id: int, user: User):
    """ Removes a publisher for an organization

    Args:
        request (HttpRequest): The incoming request
        id (int): The organization's id
        user (User): The current user object
    Returns:
         A BackendAjaxResponse since it is an Ajax request
    """
    post_params = request.POST
    group_id = int(post_params.get("publishingGroupId"))
    org = Organization.objects.get(id=id)
    group = Group.objects.get(id=group_id, publish_for_organizations=org)

    # only allow removing if the user is part of the organization or the group!
    if group not in user.groups.all() and user.organization != org:
        messages.error(request, message=PUBLISH_PERMISSION_REMOVING_DENIED)
        return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure/").get_response()
    group.publish_for_organizations.remove(org)
    messages.success(request, message=PUBLISH_PERMISSION_REMOVED.format(group.name, org.organization_name))

    return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure/").get_response()

@check_session
@check_permission(Permission(can_request_to_become_publisher=True))
def publish_request(request: HttpRequest, id: int, user: User):
    """ Performs creation of a publishing request between a user/group and an organization

    Args:
        request (HttpRequest): The incoming HttpRequest
        id (int): The organization id
        user (User): The performing user object
    Returns:
         A rendered view
    """
    template = "request_publish_permission.html"
    org = Organization.objects.get(id=id)

    request_form = PublisherForOrganization(request.POST or None)
    request_form.fields["organization_name"].initial = org.organization_name
    groups = user.groups.all().values_list('id', 'name')
    request_form.fields["group"].choices = groups
    params = {}
    if request.method == 'POST':
        if request_form.is_valid():
            msg = request_form.cleaned_data["request_msg"]
            group = Group.objects.get(id=request_form.cleaned_data["group"])

            # check if user is already a publisher using this group or a request already has been created
            pub_request = PendingRequest.objects.filter(type=PENDING_REQUEST_TYPE_PUBLISHING, organization=org, group=group)
            if org in group.publish_for_organizations.all() or pub_request.count() > 0 or org == group.organization:
                if pub_request.count() > 0:
                    messages.add_message(request, messages.INFO, PUBLISH_REQUEST_ABORTED_IS_PENDING)
                elif org == group.organization:
                    messages.add_message(request, messages.INFO, PUBLISH_REQUEST_ABORTED_OWN_ORG)
                else:
                    messages.add_message(request, messages.INFO, PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER)
                return redirect("structure:detail-organization", str(id))

            publish_request_obj = PendingRequest()
            publish_request_obj.type = PENDING_REQUEST_TYPE_PUBLISHING
            publish_request_obj.organization = org
            publish_request_obj.message = msg
            publish_request_obj.group = group
            publish_request_obj.activation_until = timezone.now() + datetime.timedelta(hours=PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW)
            publish_request_obj.save()
            # create pending publish request for organization!
            messages.add_message(request, messages.SUCCESS, PUBLISH_REQUEST_SENT)
        else:
            messages.add_message(request, messages.ERROR, FORM_INPUT_INVALID)
        return redirect("structure:detail-organization", id)

    else:
        params = {
            "form": request_form,
            "organization": org,
            "user": user,
            "button_text": _("Send"),
            "article": _("You need to ask for permission to become a publisher. Please select your group for which you want to have publishing permissions and explain why you need them."),
            "action_url": ROOT_URL + "/structure/organizations/publish-request/" + str(id),
        }

    html = render_to_string(template_name=template, context=params, request=request)
    return BackendAjaxResponse(html=html).get_response()


@check_session
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
        "permissions": user.get_permissions(),  # user_helper.get_permissions(user=user),
        "group_permissions": user.get_permissions(group),  # user_helper.get_permissions(group=group),
        "members": members,
        "show_registering_for": True,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
@check_permission(Permission(can_create_group=True))
def new_group(request: HttpRequest, user: User):
    """ Renders the new group form and saves the input

    Args:
        request: The incoming request
        user: The user object
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    if not user.has_permission(permission_needed=Permission(can_create_group=True)):
        messages.add_message(request, messages.ERROR, NO_PERMISSION)
        return redirect("structure:index")

    template = "form.html"
    form = GroupForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            group = form.save(commit=False)
            if group.parent == group:
                messages.add_message(request=request, level=messages.ERROR, message=GROUP_CAN_NOT_BE_OWN_PARENT)
            else:
                group.created_by = user
                if group.role is None:
                    group.role = Role.objects.get(name="_default_")
                group.save()
                user.groups.add(group)
            return redirect("structure:index")
        else:
            messages.error(request, message=GROUP_FORM_INVALID)
            return redirect("structure:index")
    else:
        params = {
            "form": form,
            "article": _("You are creating a new group."),
            "action_url": ROOT_URL + "/structure/groups/new/register-form/"
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()


@check_session
def list_publisher_group(request: HttpRequest, id: int, user: User):
    """ List all organizations a group can publish for

    Args:
        request: The incoming request
        id: The group id
        user: The performing user
    Returns:
        A rendered view
    """
    template = "index_publish_requests.html"
    group = Group.objects.get(id=id)

    params = {
        "group": group,
        "show_registering_for": True,
    }
    context = DefaultContext(request, params, user).get_context()
    return render(request, template, context)


@check_session
@check_permission(Permission(can_delete_group=True))
def remove_group(request: HttpRequest, user: User):
    """ Renders the remove form for a group

    Args:
        request(HttpRequest): The used request
    Returns:
        A rendered view
    """
    template = "remove_group_confirmation.html"
    group_id = request.GET.dict().get("id")
    confirmed = request.GET.dict().get("confirmed")
    group = get_object_or_404(Group, id=group_id)
    if group.created_by != user:
        messages.error(request, message=GROUP_IS_OTHERS_PROPERTY)
        return redirect("structure:detail-organization", group.id)
    permission = group.role.permission
    if confirmed == 'false':
        params = {
            "group": group,
            "permissions": permission,
        }
        html = render_to_string(template_name=template, context=params, request=request)
        return BackendAjaxResponse(html=html).get_response()
    else:

        # clean subgroups from parent
        sub_groups = Group.objects.filter(
            parent=group
        )
        for sub in sub_groups:
            sub.parent = None
            sub.save()

        # remove group and all of the related content
        group.delete()
        return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure").get_response()


@check_session
@check_permission(Permission(can_edit_group=True))
def edit_group(request: HttpRequest, user: User, id: int):
    """ The edit view for changing group values

    Args:
        request:
        id:
        user:
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    template = "form.html"
    group = Group.objects.get(id=id)
    if group.created_by != user:
        messages.error(request, message=GROUP_IS_OTHERS_PROPERTY)
        return redirect("structure:detail-organization", group.id)
    form = GroupForm(request.POST or None, instance=group)
    if request.method == "POST":
        form.fields.get('role').disabled = True
        if form.is_valid():
            # save changes of group
            group = form.save(commit=False)
            if group.parent == group:
                messages.add_message(request=request, level=messages.ERROR, message=GROUP_CAN_NOT_BE_OWN_PARENT)
            else:
                group.save()
        return redirect("structure:detail-group", group.id)

    else:
        user_perm = user.get_permissions()  # user_helper.get_permissions(user=user)
        if not 'can_change_group_role' in user_perm and form.fields.get('role', None) is not None:
            form.fields.get('role').disabled = True
        params = {
            "group": group,
            "form": form,
            "article": _("You are editing the group") + " " + group.name,
            "action_url": ROOT_URL + "/structure/groups/edit/" + str(group.id)
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()


def handler404(request: HttpRequest, exception):
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
    response = render("404.html", context=context.get_context())
    response.status_code = 404
    return response


def handler500(request: HttpRequest, exception):
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
    response = render("500.html", context=context.get_context())
    response.status_code = 500
    return response
