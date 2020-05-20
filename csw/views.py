"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.http import HttpRequest, HttpResponse


# https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
# Cache requested url for time t
#@cache_page(CSW_CACHE_TIME)
from django.views.decorators.cache import cache_page

from csw.settings import CSW_CACHE_TIME
from csw.utils.parameter import ParameterResolver

#@cache_page(CSW_CACHE_TIME, key_prefix="csw")
from csw.utils.request_resolver import RequestResolver


def resolve_request(request: HttpRequest):
    """ Wraps incoming csw request

    Args:
        request (HttpRequest): The incoming request
    Returns:

    """
    paramter = ParameterResolver(request.GET.dict())
    request_resolver = RequestResolver(paramter)

    content = request_resolver.get_response()
    content_type = paramter.output_format

    return HttpResponse(content, content_type=content_type)
