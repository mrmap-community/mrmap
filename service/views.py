from django.http import HttpRequest
from django.shortcuts import render

# Create your views here.

def index(request: HttpRequest):
    template = "index.html"
    params = {}
    return render(request=request, template_name=template, context=params)

def wms(request:HttpRequest):
    template = "index.html"
    params = {}
    return render(request=request, template_name=template, context=params)

def wfs(request:HttpRequest):
    template = "index.html"
    params = {}
    return render(request=request, template_name=template, context=params)