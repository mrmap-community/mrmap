import json
import urllib

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

# Create your views here.
from django.template.loader import render_to_string

from MapSkinner.responses import BackendAjaxResponse
from service.forms import NewServiceURIForm
from service.helper import service_helper
from service.helper.enums import ServiceTypes
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Metadata, Layer, Service, ServiceToFormat


def index(request: HttpRequest):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "index.html"
    param_GET = request.GET.dict()
    display_service_type = request.session.get("displayServices", None)
    is_root = True
    if display_service_type is not None:
        if display_service_type == 'layers':
            # show single layers instead of service grouped
            is_root = False
    md_list = Metadata.objects.filter(is_root=is_root)
    params = {
        "metadata_list": md_list,
        "select_default": request.session.get("displayServices", None)
    }
    return render(request=request, template_name=template, context=params)


def remove(request: HttpRequest):
    template = "remove_service_confirmation.html"
    service_id = request.GET.dict().get("id")
    confirmed = request.GET.dict().get("confirmed")
    service = get_object_or_404(Service, id=service_id)
    metadata = get_object_or_404(Metadata, service=service)
    if confirmed == 'false':
        params = {
            "service": service,
            "metadata": metadata
        }
        html = render_to_string(template_name=template, context=params, request=request)
        return BackendAjaxResponse(html=html).get_response()
    else:
        # remove service and all of the related content
        service.delete()
        return BackendAjaxResponse(html="", redirect="/service").get_response()


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

    if url_dict.get("service") is ServiceTypes.WMS:
        # create WMS object
        wms_factory = OGCWebMapServiceFactory()
        web_service = wms_factory.get_ogc_wms(version=url_dict["version"], service_connect_url=url_dict["base_uri"])

        # let it load it's capabilities
        web_service.create_from_capabilities()

        # check quality of metadata
        # ToDo: :3

        params = {
            "wms": web_service,
        }
        # persist data
        service_helper.persist_wms(web_service) # ToDo: Move the persisting from service helper to wms class!

    elif url_dict.get("service") is ServiceTypes.WFS:
        # create WFS object
        wfs_factory = OGCWebFeatureServiceFactory()
        wfs = wfs_factory.get_ogc_wfs(version=url_dict["version"], service_connect_url=url_dict["base_uri"])

        # load capabilities
        wfs.create_from_capabilities()

        # persist wfs
        wfs.persist()

        params = {
            "wfs": wfs,
        }
    # else:
    #     params = {}

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
    if len(layers) == 0:
        # happens only when not the parent service but the layer itself is selected
        layers = Layer.objects.filter(id=service_md.service.id)
    layers_md_list = []
    for layer in layers:
        res = {}
        md = get_object_or_404(Metadata, service=layer)
        formats = list(ServiceToFormat.objects.filter(service=layer))
        f_l = {}
        for _format in formats:
            if f_l.get(_format.action, None) is None:
                f_l[_format.action] = []
            f_l[_format.action].append(_format.mime_type)
        layer.bbox_lat_lon = json.loads(layer.bbox_lat_lon)
        res["metadata"] = md
        res["layer"] = layer
        res["formats"] = f_l
        layers_md_list.append(res)

    params = {
        "root_metadata": service_md,
        "root_service": service,
        "layer_list": layers_md_list,
    }
    return render(request=request, template_name=template, context=params)