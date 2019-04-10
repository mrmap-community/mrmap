from django.http import HttpRequest
from django.shortcuts import render


def index(request: HttpRequest):
    template = "index_structure.html"
    params = {}
    return render(request=request, template_name=template, context=params)

def groups(request:HttpRequest):
    template = "index_structure.html"
    params = {}
    return render(request=request, template_name=template, context=params)

def organizations(request:HttpRequest):
    template = "index_structure.html"
    params = {}
    return render(request=request, template_name=template, context=params)