"""MrMap URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='auth:dashboard')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='auth:dashboard')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import os

from accounts.views.auth import LoginView, LogoutView
from csw.views import CswServiceView
from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.http import Http404
from django.urls import path, re_path
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django.views.static import serve
from drf_spectacular.views import (SpectacularJSONAPIView,
                                   SpectacularSwaggerView)
from mapbender_compatibility.views import MapBenderSearchApi
from registry.proxy.resource_capabilities import \
    (WebFeatureServiceFeatureTypeCapabilities,
     WebMapServiceLayerCapabilities)
from registry.proxy.wfs_proxy import WebFeatureServiceProxy
from registry.proxy.wms_proxy import WebMapServiceProxy
from registry.views_ows.mapcontext import OwsContextView
from system.logging.formatter import SLOW_REQUEST_DUMP_SUBDIR

urlpatterns = [
    path("django-admin/", admin.site.urls),
    # translation support
    path("i18n/", include("django.conf.urls.i18n")),
    # REST API
    # registry api urls
    path("api/system/", include("system.urls", namespace="system")),
    path("api/registry/", include("registry.urls", namespace="registry")),
    path("api/accounts/", include("accounts.urls", namespace="accounts")),
    path("api/notify/", include("notify.urls", namespace="notify")),
    path("api/schema",
         cache_page(timeout=60 * 15,
                    cache="local-memory")(SpectacularJSONAPIView.as_view()),
         name="openapi-schema"),

    path('api/schema/swagger-ui',
         SpectacularSwaggerView.as_view(url_name='openapi-schema'), name='swagger-ui'),
    # ows views
    path("mrmap-proxy/wms/<uuid:pk>",
         WebMapServiceProxy.as_view(),
         name="wms-operation"),
    path("mrmap-proxy/wfs/<uuid:pk>",
         WebFeatureServiceProxy.as_view(),
         name="wfs-operation"),
    # capabilities of a single layer or feature type, the service of the resource
    # is read out of the registry over the resource, see
    # registry/proxy/resource_capabilities.py
    path("mrmap-proxy/wms/layer/<uuid:layer_pk>",
         WebMapServiceLayerCapabilities.as_view(),
         name="wms-layer-capabilities"),
    path("mrmap-proxy/wfs/featuretype/<uuid:featuretype_pk>",
         WebFeatureServiceFeatureTypeCapabilities.as_view(),
         name="wfs-featuretype-capabilities"),
    path("mrmap-proxy/ows/<int:pk>",
         OwsContextView.as_view(),
         name="ows-context-detail"),
    path('api/auth/login', LoginView.as_view()),
    path('api/auth/logout', LogoutView.as_view()),

    path("csw",
         CswServiceView.as_view(),
         name="csw-endpoint"),

    path("mapbender/search",
         MapBenderSearchApi.as_view(),
         name="mapbender-search")

]

# TODO: restrict access via authentication
# @login_required


def media_dump_not_found(request, *args, **kwargs):
    """Answers the path of a slow request dump like an unknown media file.

    The dump of a slow request carries complete sql statements, the internal host
    names which took part in answering it and the metadata of the request itself.
    Only the syslog line points at it, no page of MrMap does, so the media route
    does not serve it and an attacker is not told that the file exists (#888). A
    deployment reads its dumps on the filesystem, for as long as the sweep of
    ``system.tasks`` keeps them.

    Used by the url rule which answers the path of a dump and by
    ``protected_serve``, which answers every other spelling of that path.
    """
    raise Http404("Slow request dumps are not served.")


def _is_media_dump(path, document_root):
    """Whether the media ``path`` names one of the dumps of the syslog formatter.

    Both sides are resolved before they are compared, because ``serve`` resolves the
    path it is given the same way: a ``.`` segment, a doubled separator or a link
    which leads into the dumps must not answer a dump through this route.
    """
    root = os.path.realpath(document_root or settings.MEDIA_ROOT)
    dumps = os.path.join(root, SLOW_REQUEST_DUMP_SUBDIR)
    candidate = os.path.realpath(os.path.join(root, path))
    return candidate == dumps or candidate.startswith(dumps + os.sep)


@require_http_methods(["GET", "HEAD"])
def protected_serve(request, path, document_root=None, show_indexes=False):
    # Uploaded media is static content; any verb other than the two read verbs
    # is answered 405 here instead of reaching the file server.
    if _is_media_dump(path, document_root):
        return media_dump_not_found(request)
    return serve(request, path, document_root, show_indexes)


# the dumps are refused by a rule of their own and before the media route below, so
# that the development route which static() adds answers them the same way
urlpatterns.append(
    re_path(
        rf'^media/{SLOW_REQUEST_DUMP_SUBDIR}/.+$',
        media_dump_not_found,
        name="media-dump-not-served",
    )
)


if settings.DEBUG and not settings.TESTING:
    import debug_toolbar
    from django.conf import settings
    from django.conf.urls.static import static

    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))
    # to enable possibility to open media files during development (images, documents, etc)
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)

else:
    urlpatterns.append(
        re_path(
            r'^media/(?P<path>.*)$',
            protected_serve,
            {'document_root': settings.MEDIA_ROOT}
        ),
    )
