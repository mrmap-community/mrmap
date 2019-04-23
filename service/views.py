import urllib

from django.http import HttpRequest
from django.shortcuts import render, get_object_or_404

# Create your views here.
from django.template.loader import render_to_string

from MapSkinner.responses import BackendAjaxResponse
from service.forms import NewServiceURIForm
from service.helper import service_helper
from service.helper.ogc.wms import OGCWebMapServiceFactory
from service.models import Metadata, Layer


def index(request: HttpRequest):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "index.html"
    md_list = Metadata.objects.filter(is_root=True)
    params = {
        "metadata_list": md_list,
    }
    return render(request=request, template_name=template, context=params)


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

        params = {
            "error": error,
            "uri": url_dict["base_uri"],
            "version": url_dict["version"].value,
            "service_type": url_dict["service"].value,
            "request_action": url_dict["request"],
            "full_uri": cap_url,
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
    service_helper.persist_wms(web_service)

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
    template = "service_detail.html"
    service_md = get_object_or_404(Metadata, id=id)
    layers = Layer.objects.filter(service=service_md.service)
    layers_md_list = []
    for layer in layers:
        res = {}
        md = get_object_or_404(Metadata, service=layer)
        res["metadata"] = md
        res["layer"] = layer
        layers_md_list.append(res)

    params = {
        "root_metadata": service_md,
        "layer_list": layers_md_list,
    }
    return render(request=request, template_name=template, context=params)