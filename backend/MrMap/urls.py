"""MrMap URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='auth:dashboard')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from accounts.views.auth import LoginView, LogoutView
from csw.views import CswServiceView
from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.urls import path, re_path
from django.views.decorators.cache import cache_page
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
from system.views import MediaDumpNotFoundView, ProtectedServeView

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

# the dumps are refused by a rule of their own and before the media route below, so
# that the development route which static() adds answers them the same way
urlpatterns.append(
    re_path(
        rf'^media/{SLOW_REQUEST_DUMP_SUBDIR}/.+$',
        MediaDumpNotFoundView.as_view(),
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
                          view=ProtectedServeView.as_view(),
                          document_root=settings.MEDIA_ROOT)

else:
    urlpatterns.append(
        re_path(
            r'^media/(?P<path>.*)$',
            ProtectedServeView.as_view(),
            {'document_root': settings.MEDIA_ROOT}
        ),
    )
