"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_page
from MrMap.decorator import resolve_metadata_public_id, check_permission
from csw.forms import HarvestGroupForm
from csw.settings import CSW_CACHE_TIME, CSW_CACHE_PREFIX
from csw.utils.parameter import ParameterResolver
from csw.utils.request_resolver import RequestResolver
from service.helper.ogc.ows import OWSException
from service.models import Metadata
from structure.models import Permission


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
        metadata_id:
    Returns:

    """
    metadata = get_object_or_404(Metadata, id=metadata_id)
    form = HarvestGroupForm(data=request.POST or None,
                            request=request,
                            reverse_lookup='csw:harvest-catalogue',
                            reverse_args=[metadata_id, ],
                            # ToDo: after refactoring of all forms is done, show_modal can be removed
                            show_modal=True,
                            form_title=_(f"Harvest <strong>{metadata}</strong>"),
                            instance=metadata)
    return form.process_request(valid_func=form.process_harvest_catalogue)
