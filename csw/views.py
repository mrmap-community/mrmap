"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.http import HttpRequest, HttpResponse

from pycsw import server as pycsw_server

from MapSkinner.settings import PYCSW_CONF


def resolve_request(request: HttpRequest):
    """ Wraps incoming csw request

    Args:
        request (HttpRequest): The incoming request
    Returns:

    """
    conf = PYCSW_CONF

    version = request.GET.get("version", "2.0.2")
    csw = pycsw_server.Csw(conf, request.META, version=version)

    content = csw.dispatch_wsgi()

    # pycsw API return value differs between >=2.x and <2.x
    # response contains in >=2.x the status code at [0] and the "real" content at [1]
    if int(version[0]) >= 2:
        content = content[1]

    return HttpResponse(content, content_type=csw.contenttype)
