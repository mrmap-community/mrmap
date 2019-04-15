from django.http import HttpRequest
from django.shortcuts import render

# Create your views here.


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