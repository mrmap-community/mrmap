"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""

from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from MrMap.messages import HARVEST_RUN_SCHEDULED
from csw.forms import HarvestRunForm
from csw.models import HarvestResult
from csw.settings import CSW_CACHE_TIME, CSW_CACHE_PREFIX
from csw.utils.parameter import ParameterResolver
from extras.views import SecuredCreateView


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
        # FIXME
        request_resolver = None
        #request_resolver = RequestResolver(paramter)
        content = request_resolver.get_response()
        content_type = paramter.output_format
    except Exception as e:
        # FIXME
        #ows_exception = OWSException(e)
        #content = ows_exception.get_exception_report()
        content_type = "application/xml"

    return HttpResponse(content, content_type=content_type)


class HarvestRunNewView(SecuredCreateView):
    model = HarvestResult
    form_class = HarvestRunForm
    success_message = HARVEST_RUN_SCHEDULED
    # FIXME: wrong success_url
    #success_url = reverse_lazy('resource:pending-tasks')

