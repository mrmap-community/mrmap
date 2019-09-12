import json

import time
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from MapSkinner import utils
from MapSkinner.decorator import check_session, check_permission
from MapSkinner.messages import FORM_INPUT_INVALID, SERVICE_UPDATE_WRONG_TYPE, \
    SERVICE_REMOVED, SERVICE_ACTIVATED, SERVICE_UPDATED, SERVICE_DEACTIVATED
from MapSkinner.responses import BackendAjaxResponse, DefaultContext
from MapSkinner.settings import ROOT_URL
from service import tasks
from service.forms import ServiceURIForm
from service.helper import service_helper, update_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import ServiceTypes
from service.helper.service_comparator import ServiceComparator
from service.models import Metadata, Layer, Service, FeatureType, CapabilityDocument
from service.tasks import async_remove_service_task
from structure.models import User, Permission, PendingTask, Group
from users.helper import user_helper


@check_session
def index(request: HttpRequest, user: User, service_type=None):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
        user (User): The session user
        service_type: Indicates if only a special service type shall be displayed
    Returns:
         A view
    """
    template = "service_index.html"

    # possible results per page values
    rpp_select = [5, 10, 15, 20]
    try:
        wms_page = int(request.GET.get("wmsp", 1))
        wfs_page = int(request.GET.get("wfsp", 1))
        results_per_page = int(request.GET.get("rpp", 5))
        if wms_page < 1 or wfs_page < 1 or results_per_page < 1:
            raise ValueError
        if results_per_page not in rpp_select:
            results_per_page = 5
    except ValueError as e:
        # since parameters could be changed directly in the uri, we need to make sure to avoid problems
        return redirect("service:index")

    # whether whole services or single layers should be displayed
    display_service_type = request.session.get("displayServices", None)
    is_root = True
    if display_service_type is not None:
        is_root = display_service_type != "layers"

    # get services
    paginator_wms = None
    paginator_wfs = None
    if service_type is None or service_type == ServiceTypes.WMS.value:
        md_list_wms = Metadata.objects.filter(
            service__servicetype__name="wms",
            service__is_root=is_root,
            created_by__in=user.groups.all(),
            service__is_deleted=False,
        ).order_by("title")
        paginator_wms = Paginator(md_list_wms, results_per_page).get_page(wms_page)
    if service_type is None or service_type == ServiceTypes.WFS.value:
        md_list_wfs = Metadata.objects.filter(
            service__servicetype__name="wfs",
            created_by__in=user.groups.all(),
            service__is_deleted=False,
        ).order_by("title")
        paginator_wfs = Paginator(md_list_wfs, results_per_page).get_page(wfs_page)

    # get pending tasks
    pending_tasks = PendingTask.objects.filter(created_by__in=user.groups.all())
    for task in pending_tasks:
        task.description = json.loads(task.description)
    params = {
        "metadata_list_wms": paginator_wms,
        "metadata_list_wfs": paginator_wfs,
        "select_default": request.session.get("displayServices", None),
        "only_type": service_type,
        "user": user,
        "rpp_select_options": rpp_select,
        "rpp": results_per_page,
        "pending_tasks": pending_tasks,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
@check_permission(Permission(can_remove_service=True))
def remove(request: HttpRequest, user: User):
    """ Renders the remove form for a service

    Args:
        request(HttpRequest): The used request
    Returns:
        A rendered view
    """
    template = "overlay/remove_service_confirmation.html"
    service_id = request.GET.dict().get("id")
    confirmed = request.GET.dict().get("confirmed")
    service = get_object_or_404(Service, id=service_id)
    service_type = service.servicetype
    sub_elements = None
    if service_type.name == ServiceTypes.WMS.value:
        sub_elements = Layer.objects.filter(parent_service=service)
    elif service_type.name == ServiceTypes.WFS.value:
        sub_elements = service.featuretypes.all()
    metadata = get_object_or_404(Metadata, service=service)
    if confirmed == 'false':
        params = {
            "service": service,
            "metadata": metadata,
            "sub_elements": sub_elements,
        }
        html = render_to_string(template_name=template, context=params, request=request)
        return BackendAjaxResponse(html=html).get_response()
    else:
        # remove service and all of the related content
        user_helper.create_group_activity(metadata.created_by, user, SERVICE_REMOVED, metadata.title)

        # set service as deleted, so it won't be listed anymore in the index view until completely removed
        service.is_deleted = True
        service.save()

        # call removing as async task
        async_remove_service_task.delay(service_id)

        return BackendAjaxResponse(html="", redirect=ROOT_URL + "/service").get_response()

@check_session
@check_permission(Permission(can_activate_service=True))
def activate(request: HttpRequest, user:User):
    """ (De-)Activates a service and all of its layers

    Args:
        request:
    Returns:
         An Ajax response
    """
    param_POST = request.POST.dict()
    service_id = param_POST.get("id", -1)
    new_status = utils.resolve_boolean_attribute_val(param_POST.get("active", False))
    # get service and change status
    service = Service.objects.get(id=service_id)
    service.metadata.is_active = new_status
    service.metadata.save()
    # get root_layer of service and start changing of all statuses
    if service.servicetype == "wms":
        root_layer = Layer.objects.get(parent_service=service, parent_layer=None)
        service_helper.activate_layer_recursive(root_layer, new_status)

    if service.metadata.is_active:
        msg = SERVICE_ACTIVATED
    else:
        msg = SERVICE_DEACTIVATED
    user_helper.create_group_activity(service.metadata.created_by, user, msg, service.metadata.title)

    return BackendAjaxResponse(html="", redirect=ROOT_URL + "/service").get_response()


def get_capabilities(request: HttpRequest, id: int):
    """ Returns the current capabilities xml file

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    cap_doc = CapabilityDocument.objects.get(related_metadata__id=id)
    doc = cap_doc.current_capability_document
    return HttpResponse(doc, content_type='application/xml')


def get_capabilities_original(request: HttpRequest, id: int):
    """ Returns the current capabilities xml file

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    cap_doc = CapabilityDocument.objects.get(related_metadata__id=id)
    doc = cap_doc.original_capability_document
    return HttpResponse(doc, content_type='application/xml')


@check_session
def session(request: HttpRequest, user:User):
    """ Can set a value to the django session

    Args:
        request:
    Returns:
    """
    param_GET = request.GET.dict()
    _session = param_GET.get("session", None)
    if _session is None:
        return BackendAjaxResponse(html="").get_response()
    _session = json.loads(_session)
    for _session_key, _session_val in _session.items():
        request.session[_session_key] = _session_val
    return BackendAjaxResponse(html="").get_response()

@check_session
def wms(request:HttpRequest, user:User):
    """ Renders an overview of all wms

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    return redirect("service:index", ServiceTypes.WMS.value)


@check_session
@check_permission(Permission(can_register_service=True))
def register_form(request: HttpRequest, user: User):
    """ Returns the form for providing a capabilities URI

    Args:
        request:
    Returns:
        BackendAjaxResponse
    """
    template = "overlay/service_url_form.html"
    POST_params = request.POST.dict()
    if POST_params.get("uri", None) is not None:

        error = False
        cap_url = POST_params.get("uri", "")
        url_dict = service_helper.split_service_uri(cap_url)

        if url_dict["request"].lower() != "getcapabilities":
            # not allowed!
            error = True

        try:
            # create group->publishable organizations dict
            group_orgs = {}
            for group in user.groups.all():
                group_orgs[group.id] = list(group.publish_for_organizations.all().values_list("id", flat=True))
            params = {
                "error": error,
                "uri": url_dict["base_uri"],
                "version": url_dict["version"].value,
                "service_type": url_dict["service"].value,
                "request_action": url_dict["request"],
                "full_uri": cap_url,
                "user": user,
                "group_publishable_orgs": json.dumps(group_orgs),
                "page_indicator_list": [False, True, False],
            }
        except AttributeError as e:
            params = {
                "error": e,
            }

        template = "overlay/register_new_service.html"
    else:
        uri_form = ServiceURIForm()
        params = {
            "form": uri_form,
            "action_url": ROOT_URL + "/service/new/register-form",
            "button_text": "Next",
            "page_indicator_list": [True, False, False],
        }
    html = render_to_string(request=request, template_name=template, context=params)
    return BackendAjaxResponse(html).get_response()


@check_session
@check_permission(Permission(can_register_service=True))
def new_service(request: HttpRequest, user: User):
    """ Register a new service

    Args:
        request:
    Returns:

    """
    POST_params = request.POST.dict()

    cap_url = POST_params.get("uri", "")
    cap_url = cap_url.replace("&amp;", "&")
    register_group = POST_params.get("registerGroup")
    register_for_organization = POST_params.get("registerForOrg")

    url_dict = service_helper.split_service_uri(cap_url)
    url_dict["service"] = url_dict["service"].value
    url_dict["version"] = url_dict["version"].value

    # run creation async!
    pending_task = tasks.async_new_service.delay(url_dict, user.id, register_group, register_for_organization)
    #pending_task = tasks.async_new_service(url_dict, user.id, register_group, register_for_organization)

    # create db object, so we know which pending task is still ongoing
    pending_task_db = PendingTask()
    pending_task_db.created_by = Group.objects.get(id=register_group)
    pending_task_db.task_id = pending_task.task_id
    pending_task_db.description = json.dumps({
        "service": cap_url,
        "phase": "parsing",
    })

    pending_task_db.save()

    params = {
        "pending_task": pending_task,
        "url_dict": url_dict,
        "page_indicator_list": [False, False, True],
    }

    template = "overlay/new_service_progress.html"
    html = render_to_string(template_name=template, request=request, context=params)
    return BackendAjaxResponse(html=html).get_response()


@check_session
@check_permission(Permission(can_update_service=True))
@transaction.atomic
def update_service(request: HttpRequest, user: User, id: int):
    """ Compare old service with new service and collect differences

    Args:
        request: The incoming request
        user: The active user
        id: The service id
    Returns:
        A rendered view
    """
    template = "service_differences.html"
    update_params = request.session["update"]
    url_dict = service_helper.split_service_uri(update_params["full_uri"])
    new_service_type = url_dict.get("service")
    old_service = Service.objects.get(id=id)

    # check if metadata should be kept
    keep_custom_metadata = request.POST.get("keep-metadata", None)
    if keep_custom_metadata is None:
        keep_custom_metadata = request.session.get("keep-metadata", "")
    request.session["keep-metadata"] = keep_custom_metadata
    keep_custom_metadata = keep_custom_metadata == "on"


    # get info which layers/featuretypes are linked (old->new)
    links = json.loads(request.POST.get("storage", '{}'))
    update_confirmed = utils.resolve_boolean_attribute_val(request.POST.get("confirmed", 'false'))

    # parse new capabilities into db model
    registrating_group = old_service.created_by
    new_service = service_helper.get_service_model_instance(service_type=url_dict.get("service"), version=url_dict.get("version"), base_uri=url_dict.get("base_uri"), user=user, register_group=registrating_group)
    xml = new_service["raw_data"].service_capabilities_xml
    new_service = new_service["service"]

    # Collect differences
    comparator = ServiceComparator(service_1=new_service, service_2=old_service)
    diff = comparator.compare_services()

    if update_confirmed:
        # check cross service update attempt
        if old_service.servicetype.name != new_service_type.value:
            # cross update attempt -> forbidden!
            messages.add_message(request, messages.ERROR, SERVICE_UPDATE_WRONG_TYPE)
            return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL, str(old_service.metadata.id))).get_response()
        # check if new capabilities is even different from existing
        # if not we do not need to spend time and money on performing it!
        # if not service_helper.capabilities_are_different(update_params["full_uri"], old_service.metadata.original_uri):
        #     messages.add_message(request, messages.INFO, SERVICE_UPDATE_ABORTED_NO_DIFF)
        #     return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL, str(old_service.metadata.id))).get_response()

        if not keep_custom_metadata:
            # the update is confirmed, we can continue changing the service!
            # first update the metadata of the whole service
            md = update_helper.update_metadata(old_service.metadata, new_service.metadata)
            old_service.metadata = md
            # don't forget the timestamp when we updated the last time
            old_service.metadata.last_modified = timezone.now()
            # save the metadata changes
            old_service.metadata.save()
        # secondly update the service itself, overwrite the metadata with the previously updated metadata
        old_service = update_helper.update_service(old_service, new_service)
        old_service.last_modified = timezone.now()

        if new_service.servicetype.name == ServiceTypes.WFS.value:
            old_service = update_helper.update_wfs(old_service, new_service, diff, links, keep_custom_metadata)

        elif new_service.servicetype.name == ServiceTypes.WMS.value:
            old_service = update_helper.update_wms(old_service, new_service, diff, links, keep_custom_metadata)

        cap_document = CapabilityDocument.objects.get(related_metadata=old_service.metadata)
        cap_document.current_capability_document = xml
        cap_document.save()

        old_service.save()
        del request.session["keep-metadata"]
        del request.session["update"]
        user_helper.create_group_activity(old_service.metadata.created_by, user, SERVICE_UPDATED, old_service.metadata.title)
        return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL,str(old_service.metadata.id))).get_response()
    else:
        # otherwise
        params = {
            "diff": diff,
            "old_service": old_service,
            "new_service": new_service,
            "page_indicator_list": [False, True],
        }
        #request.session["update_confirmed"] = True
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


@check_session
def discard_update(request: HttpRequest, user: User):
    """ If the user does not want to proceed with the update,
    we need to go back and drop the session stored data about the update

    Args:
        request (HttpRequest):
        user (User):
    Returns:
         redirects
    """
    del request.session["update"]
    return redirect("service:index")


@check_session
@check_permission(Permission(can_update_service=True))
def update_service_form(request: HttpRequest, user:User, id: int):
    """ Creates the form for updating a service

    Args:
        request: The incoming request
        user: The current user
        id: The service id
    Returns:
         A BackendAjaxResponse
    """
    template = "overlay/service_url_form.html"
    uri_form = ServiceURIForm(request.POST or None)
    params = {}
    if request.method == 'POST':
        template = "overlay/update_service.html"
        if uri_form.is_valid():
            error = False
            cap_url = uri_form.data.get("uri", "")
            url_dict = service_helper.split_service_uri(cap_url)

            if url_dict["request"] != "GetCapabilities":
                # not allowed!
                error = True

            try:
                # get current service to compare with
                service = Service.objects.get(id=id)
                params = {
                    "action_url": ROOT_URL + "/service/update/" + str(id),
                    "service": service,
                    "error": error,
                    "uri": url_dict["base_uri"],
                    "version": url_dict["version"].value,
                    "service_type": url_dict["service"].value,
                    "request_action": url_dict["request"],
                    "full_uri": cap_url,
                    "page_indicator_list": [False, True],
                }
                request.session["update"] = {
                    "full_uri": cap_url,
                }
            except AttributeError:
                params = {
                    "error": error,
                    "page_indicator_list": [False, True],
                }

        else:
            params = {
                "error": FORM_INPUT_INVALID,
                "page_indicator_list": [False, True],
            }

    else:
        params = {
            "form": uri_form,
            "article": _("Enter the new capabilities URL of your service."),
            "action_url": ROOT_URL + "/service/register-form/" + str(id),
            "button_text": "Update",
            "page_indicator_list": [True, False],
        }
    params["service_id"] = id
    html = render_to_string(template_name=template, request=request, context=params)
    return BackendAjaxResponse(html=html).get_response()


@check_session
def wfs(request:HttpRequest, user:User):
    """ Renders an overview of all wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    params = {
        "only": ServiceTypes.WFS
    }
    return redirect("service:index", ServiceTypes.WFS.value)


@check_session
def detail(request: HttpRequest, id, user:User):
    """ Renders a detail view of the selected service

    Args:
        request: The incoming request
        id: The id of the selected metadata
    Returns:
    """
    template = "detail/service_detail.html"
    service_md = get_object_or_404(Metadata, id=id)
    service = get_object_or_404(Service, id=service_md.service.id)
    layers = Layer.objects.filter(parent_service=service_md.service)
    layers_md_list = layers.filter(parent_layer=None)
    params = {
        "root_metadata": service_md,
        "root_service": service,
        "layers": layers_md_list,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
def detail_child(request: HttpRequest, id, user:User):
    elementType = request.GET.get("serviceType")
    if elementType == "wms":
        template = "detail/service_detail_child_wms.html"
        element = Layer.objects.get(id=id)
    elif elementType == "wfs":
        template = "detail/service_detail_child_wfs.html"
        element = FeatureType.objects.get(id=id)
    else:
        template = ""
        element = None
    params = {
        "element": element,
        "user_permissions": user.get_permissions(),
    }
    html = render_to_string(template_name=template, context=params)
    return BackendAjaxResponse(html=html).get_response()


def metadata_proxy(request: HttpRequest, id: int):
    """ Returns the xml document which is resolved by the metadata id.

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         HttpResponse
    """
    dataset_metadata = Metadata.objects.get(id=id)
    con = CommonConnector(url=dataset_metadata.metadata_url)
    con.load()
    xml_raw = con.content
    return HttpResponse(xml_raw, content_type='application/xml')
