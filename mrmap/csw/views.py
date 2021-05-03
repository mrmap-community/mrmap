"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView

from MrMap.messages import HARVEST_RUN_SCHEDULED, NO_PERMISSION
from MrMap.views import GenericViewContextMixin, InitFormMixin
from csw.forms import HarvestRunForm
from csw.models import HarvestResult
from csw.settings import CSW_CACHE_TIME, CSW_CACHE_PREFIX
from csw.utils.parameter import ParameterResolver
from csw.utils.request_resolver import RequestResolver
from service.helper.ogc.ows import OWSException
from structure.permissionEnums import PermissionEnum

@csrf_exempt
@cache_page(CSW_CACHE_TIME, key_prefix=CSW_CACHE_PREFIX)
def get_csw_results(request: HttpRequest):
    """ Wraps incoming csw request

    Args:
        request (HttpRequest): The incoming request
    Returns:

    """

    try:
        paramter = ParameterResolver(request.GET.dict())
        request_resolver = RequestResolver(paramter)
        content = request_resolver.get_response()
        content_type = paramter.output_format
    except Exception as e:
        ows_exception = OWSException(e)
        content = ows_exception.get_exception_report()
        content_type = "application/xml"

    return HttpResponse(content, content_type=content_type)


class HarvestRunNewView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
    model = HarvestResult
    form_class = HarvestRunForm
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('New harvest run')
    success_message = HARVEST_RUN_SCHEDULED
    permission_required = PermissionEnum.CAN_HARVEST.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION
    success_url = reverse_lazy('resource:pending-tasks')

