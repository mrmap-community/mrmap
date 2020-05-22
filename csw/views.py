"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse

# https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
# Cache requested url for time t
#@cache_page(CSW_CACHE_TIME)
from django.views.decorators.cache import cache_page

from csw.settings import CSW_CACHE_TIME
from csw.utils.parameter import ParameterResolver

#@cache_page(CSW_CACHE_TIME, key_prefix="csw")
from csw.utils.request_resolver import RequestResolver
from service.helper.ogc.ows import OWSException


def get_csw_results(request: HttpRequest):
    """ Wraps incoming csw request

    Args:
        request (HttpRequest): The incoming request
    Returns:

    """
    paramter = ParameterResolver(request.GET.dict())
    request_resolver = RequestResolver(paramter)

    try:
        content = request_resolver.get_response()
        content_len = len(content)
    except Exception as e:
        ows_exception = OWSException(e)
        content = ows_exception.get_exception_report()
        content_len = -1
    content_type = paramter.output_format

    if content_len > 1000000:
        return StreamingHttpResponse(content, content_type=content_type)
    else:
        return HttpResponse(content, content_type=content_type)
