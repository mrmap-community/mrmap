"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from django.views.decorators.cache import cache_page

from MrMap.decorator import resolve_metadata_public_id, check_permission
from MrMap.messages import RESOURCE_NOT_FOUND
from csw.settings import CSW_CACHE_TIME, CSW_CACHE_PREFIX
from csw.tasks import async_harvest
from csw.utils.parameter import ParameterResolver

from csw.utils.request_resolver import RequestResolver
from service.helper.enums import MetadataEnum
from service.helper.ogc.ows import OWSException

# https://docs.djangoproject.com/en/dev/topics/cache/#the-per-view-cache
# Cache requested url for time t
from service.helper.service_helper import split_service_uri
from service.models import Metadata
from service.tasks import async_new_service
from structure.models import PendingTask, Permission
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
@resolve_metadata_public_id
@check_permission(
    Permission(
        can_harvest=True
    )
)
def harvest_catalogue(request: HttpRequest, metadata_id: str):
    """ Starts harvesting procedure for catalogue

    Args:
        request (HttpRequest): The incoming request
    Returns:

    """
    # ToDo: Nice Frontend here please!
    user = user_helper.get_user(request)
    harvesting_group = user.get_groups().filter(
        is_public_group=False
    ).first()

    # Check if the catalogue exists
    try:
        md = Metadata.objects.get(
            id=metadata_id,
            metadata_type=MetadataEnum.CATALOGUE.value
        )
        # Check for a running pending task on this catalogue!
        try:
            p_t = PendingTask.objects.get(
                task_id=str(md.id)
            )
            messages.info(
                request,
                "Harvesting is already running. Remaining time: {}".format(p_t.remaining_time)
            )
        except ObjectDoesNotExist:
            # No pending task exists, so we can start a harvesting process!
            async_harvest.delay(
                metadata_id,
                harvesting_group.id
            )
            messages.success(
                request,
                "Harvesting starts!"
            )
    except ObjectDoesNotExist:
        messages.error(
            request,
            RESOURCE_NOT_FOUND
        )

    return redirect("resource:index")
