from django.http import HttpRequest
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from user.forms import LoginForm


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

def login(request:HttpRequest):
    template = "login.html"
    login_form = LoginForm()
    params = {
        "login_form": login_form,
        "login_article_title": _("Sign in for Mr. Map"),
        "login_article": _("Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. ")
    }
    return render(request=request, template_name=template, context=params)