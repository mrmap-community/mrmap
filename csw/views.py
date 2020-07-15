"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse

from django.views.decorators.cache import cache_page

from MrMap.decorator import resolve_metadata_public_id
from MrMap.messages import RESOURCE_NOT_FOUND
from csw.settings import CSW_CACHE_TIME, CSW_CACHE_PREFIX
from csw.utils.harvester import Harvester
from csw.utils.parameter import ParameterResolver

from csw.utils.request_resolver import RequestResolver
from service.helper.enums import MetadataEnum
from service.helper.ogc.ows import OWSException


# https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
# Cache requested url for time t
from service.helper.service_helper import split_service_uri
from service.models import Metadata
from service.tasks import async_new_service
from structure.models import MrMapUser
from users.helper import user_helper


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


@login_required
def add_new_catalogue(request: HttpRequest):
    """ Registration route for new CSW records

    Args:
        request (HttpRequest): The incoming request
    Returns:

    """
    post_params = request.POST.dict()
    user = user_helper.get_user(request)

    csw_uri = post_params.get("uri", None)
    if csw_uri is not None:
        uri_dict = split_service_uri(csw_uri)
        uri_dict["service"] = uri_dict["service"].value
        async_new_service(
            url_dict=uri_dict,
            user_id=user.id,
            register_group_id=1,
            register_for_organization_id=None,
            external_auth=None
        )

    return HttpResponse()


@login_required
@resolve_metadata_public_id
def harvest_catalogue(request: HttpRequest, metadata_id: str):
    """ Starts harvesting procedure for catalogue

    Args:
        request (HttpRequest): The incoming request
    Returns:

    """
    try:
        md = Metadata.objects.get(
            id=metadata_id,
            metadata_type=MetadataEnum.CATALOGUE.value
        )
        harvester = Harvester(md)
        harvester.harvest()
    except ObjectDoesNotExist:
        return HttpResponse(RESOURCE_NOT_FOUND, status=404)
    return HttpResponse()