import json

from django.http import HttpRequest
from django.shortcuts import render, get_object_or_404, redirect

from django.template.loader import render_to_string

from MapSkinner.decorator import check_access
from MapSkinner.responses import BackendAjaxResponse
from service.forms import NewServiceURIForm
from service.helper import service_helper
from service.helper.enums import ServiceTypes
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Metadata, Layer, Service
from structure.helper import user_helper
from structure.models import User
from django.utils.translation import gettext_lazy as _


@check_access
def index(request: HttpRequest, user: User, service_type=None):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
        user (User): The session user
        service_type: Indicates if only a special service type shall be displayed
    Returns:
         A view
    """
    template = "index.html"
    display_service_type = request.session.get("displayServices", None)
    is_root = True
    if display_service_type is not None:
        if display_service_type == 'layers':
            # show single layers instead of grouped service
            is_root = False
    md_list_wfs = None
    md_list_wms = None
    if service_type is None or service_type == ServiceTypes.WMS.value:
        md_list_wms = Metadata.objects.filter(
            service__servicetype__name="wms",
            service__is_root=is_root,
            service__published_by=user.primary_organization,
            service__is_deleted=False,
        )
    if service_type is None or service_type == ServiceTypes.WFS.value:
        md_list_wfs = Metadata.objects.filter(
            service__servicetype__name="wfs",
            service__published_by=user.primary_organization,
            service__is_deleted=False,
        )
    params = {
        "metadata_list_wms": md_list_wms,
        "metadata_list_wfs": md_list_wfs,
        "select_default": request.session.get("displayServices", None),
        "only_type": service_type,
        "permissions": user_helper.get_permissions(user),
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
    template = "remove_service_confirmation.html"
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
        service.is_deleted = True
        service.save()
        #service.delete()
        return BackendAjaxResponse(html="", redirect="/service").get_response()

@check_access
def activate(request: HttpRequest, user:User):
    """ (De-)Activates a service and all of its layers

    Args:
        request:
    Returns:
         An Ajax response
    """
    param_POST = request.POST.dict()
    service_id = param_POST.get("id", -1)
    new_status = service_helper.resolve_boolean_attribute_val(param_POST.get("active", False))
    # get service and change status
    service = Service.objects.get(id=service_id)
    service.metadata.is_active = new_status
    service.metadata.save()
    # get root_layer of service and start changing of all statuses
    root_layer = Layer.objects.get(parent_service=service, parent_layer=None)
    service_helper.change_layer_status_recursively(root_layer, new_status)

    return BackendAjaxResponse(html="").get_response()

@check_access
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

@check_access
def wms(request:HttpRequest, user:User):
    """ Renders an overview of all wms

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    return redirect("service:index", ServiceTypes.WMS.value)

@check_access
def register_form(request: HttpRequest, user:User):
    """ Returns the form for providing a capabilities URI

    Args:
        request:
    Returns:
        BackendAjaxResponse
    """
    template = "new_service_url_form.html"
    POST_params = request.POST.dict()
    if POST_params.get("uri", None) is not None:

        error = False
        cap_url = POST_params.get("uri", "")
        url_dict = service_helper.split_service_uri(cap_url)

        if url_dict["request"] != "GetCapabilities":
            # not allowed!
            error = True

        try:
            params = {
                "error": error,
                "uri": url_dict["base_uri"],
                "version": url_dict["version"].value,
                "service_type": url_dict["service"].value,
                "request_action": url_dict["request"],
                "full_uri": cap_url,
            }
        except AttributeError:
            params = {
                "error": error,
            }

        template = "register_new_service.html"
    else:
        uri_form = NewServiceURIForm()
        params = {
            "form": uri_form,
        }
    html = render_to_string(request=request, template_name=template, context=params)
    return BackendAjaxResponse(html).get_response()

@check_access
def new_service(request: HttpRequest, user:User):
    """ Register a new service

    Args:
        request:
    Returns:

    """
    POST_params = request.POST.dict()
    cap_url = POST_params.get("uri", "")
    user = user_helper.get_user(user_id=request.session.get("user_id"))
    url_dict = service_helper.split_service_uri(cap_url)

    params = {}

    if url_dict.get("service") is ServiceTypes.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        try:
            wms = wms_factory.get_ogc_wms(version=url_dict["version"], service_connect_url=url_dict["base_uri"])
            # let it load it's capabilities
            wms.create_from_capabilities()

            # check quality of metadata
            # ToDo: :3

            params["service"] = wms
            # persist data

            wms.persist(user)
        except ConnectionError as e:
            params["error"] = e.args[0]
            return

    elif url_dict.get("service") is ServiceTypes.WFS:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        try:
            wfs = wfs_factory.get_ogc_wfs(version=url_dict["version"], service_connect_url=url_dict["base_uri"])
            # load capabilities
            wfs.create_from_capabilities()

            params["service"] = wfs

            # persist wfs
            wfs.persist(user)
        except ConnectionError as e:
            params["error"] = e.args[0]

    template = "check_metadata_form.html"
    html = render_to_string(template_name=template, request=request, context=params)
    return BackendAjaxResponse(html=html).get_response()

@check_access
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

@check_access
def detail(request: HttpRequest, id, user:User):
    """ Renders a detail view of the selected service

    Args:
        request: The incoming request
        id: The id of the selected service
    Returns:
    """
    template = "service_detail.html"
    service_md = get_object_or_404(Metadata, id=id)
    service = get_object_or_404(Service, id=service_md.service.id)
    layers = Layer.objects.filter(parent_service=service_md.service)
    layers_md_list = layers.filter(parent_layer=None)
    params = {
        "root_metadata": service_md,
        "root_service": service,
        "layers": layers_md_list,
        "permissions": user_helper.get_permissions(user),
    }
    return render(request=request, template_name=template, context=params)