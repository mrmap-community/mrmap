"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.http import HttpRequest, HttpResponse

from django.views.decorators.cache import cache_page

from csw.settings import CSW_CACHE_TIME, CSW_CACHE_PREFIX
from csw.utils.parameter import ParameterResolver

from csw.utils.request_resolver import RequestResolver
from service.helper.ogc.ows import OWSException


# https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
# Cache requested url for time t
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
