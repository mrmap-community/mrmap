import urllib

from django.http import HttpRequest
from django.shortcuts import render

# Create your views here.
from django.template.loader import render_to_string

from MapSkinner.responses import BackendAjaxResponse
from service.forms import NewServiceURIForm
from service.helper import service_helper
from service.helper.ogc.wms import OGCWebMapService_1_1_1


def index(request: HttpRequest):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "index.html"
    params = {}
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

    web_service = OGCWebMapService_1_1_1(service_connect_url=url_dict["base_uri"],
                                         service_version=url_dict["version"],
                                         service_type=url_dict["service"])
    web_service.create_from_capabilities()
    params = {
    }

    template = "register_new_service.html"
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