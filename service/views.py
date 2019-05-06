import json
import time

from django.http import HttpRequest
from django.shortcuts import render, get_object_or_404

from django.template.loader import render_to_string

from MapSkinner.responses import BackendAjaxResponse
from MapSkinner.settings import EXEC_TIME_PRINT
from service.forms import NewServiceURIForm
from service.helper import service_helper
from service.helper.enums import ServiceTypes
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Metadata, Layer, Service, ServiceToFormat, ServiceType


def index(request: HttpRequest):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "index.html"
    display_service_type = request.session.get("displayServices", None)
    is_root = True
    if display_service_type is not None:
        if display_service_type == 'layers':
            # show single layers instead of service grouped
            is_root = False
    md_list_wms = Metadata.objects.filter(service__servicetype__name="wms", is_root=is_root)
    md_list_wfs = Metadata.objects.filter(service__servicetype__name="wfs")
    params = {
        "metadata_list_wms": md_list_wms,
        "metadata_list_wfs": md_list_wfs,
        "select_default": request.session.get("displayServices", None)
    }
    return render(request=request, template_name=template, context=params)


def remove(request: HttpRequest):
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
    service_layers = Layer.objects.filter(parent_service=service)
    metadata = get_object_or_404(Metadata, service=service)
    if confirmed == 'false':
        params = {
            "service": service,
            "metadata": metadata,
            "service_layers": service_layers,
        }
        html = render_to_string(template_name=template, context=params, request=request)
        return BackendAjaxResponse(html=html).get_response()
    else:
        # remove service and all of the related content
        service.delete()
        return BackendAjaxResponse(html="", redirect="/service").get_response()

def activate(request: HttpRequest):
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

def session(request: HttpRequest):
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


def wms(request:HttpRequest):
    """ Renders an overview of all wms

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "index.html"
    params = {}
    return render(request=request, template_name=template, context=params)


def register_form(request: HttpRequest):
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


def new_service(request: HttpRequest):
    """ Register a new service

    Args:
        request:
    Returns:

    """
    POST_params = request.POST.dict()
    cap_url = POST_params.get("uri", "")
    url_dict = service_helper.split_service_uri(cap_url)
    epsg_api = EpsgApi()
    epsg_api.get_axis_order("EPSG:25832")

    if url_dict.get("service") is ServiceTypes.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        wms = wms_factory.get_ogc_wms(version=url_dict["version"], service_connect_url=url_dict["base_uri"])

        # let it load it's capabilities
        wms.create_from_capabilities()

        # check quality of metadata
        # ToDo: :3

        params = {
            "service": wms,
        }
        # persist data

        start_time = time.time()
        wms.persist()
        print(EXEC_TIME_PRINT % ("persisting", time.time() - start_time))

    elif url_dict.get("service") is ServiceTypes.WFS:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=url_dict["version"], service_connect_url=url_dict["base_uri"])

        # load capabilities
        wfs.create_from_capabilities()

        # persist wfs
        wfs.persist()

        params = {
            "service": wfs,
        }

    template = "check_metadata_form.html"
    html = render_to_string(template_name=template, request=request, context=params)
    return BackendAjaxResponse(html=html).get_response()


def wfs(request:HttpRequest):
    """ Renders an overview of all wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "index.html"
    params = {}
    return render(request=request, template_name=template, context=params)


def detail(request: HttpRequest, id):
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
    }
    return render(request=request, template_name=template, context=params)