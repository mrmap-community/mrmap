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

from accounts.views.auth import LoginView, LogoutView
from csw.views import CswServiceView
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.cache import cache_page
from drf_spectacular.views import (SpectacularJSONAPIView,
                                   SpectacularSwaggerView)
from registry.proxy.wfs_proxy import WebFeatureServiceProxy
from registry.proxy.wms_proxy import WebMapServiceProxy
from registry.views_ows.mapcontext import OwsContextView

urlpatterns = [
    path("django-admin/", admin.site.urls),
    # captcha support
    path("captcha/", include("captcha.urls")),
    # translation support
    path("i18n/", include("django.conf.urls.i18n")),
    # REST API
    # registry api urls
    path("api/registry/", include("registry.urls", namespace="registry")),
    path("api/accounts/", include("accounts.urls", namespace="accounts")),
    path("api/notify/", include("notify.urls", namespace="notify")),
    path(
        "api/schema",
        cache_page(timeout=60 * 15,
                   cache="local-memory")(SpectacularJSONAPIView.as_view()),
        name="openapi-schema"),

    path('api/schema/swagger-ui',
         SpectacularSwaggerView.as_view(url_name='openapi-schema'), name='swagger-ui'),
    # ows views
    path(
        "mrmap-proxy/wms/<pk>",
        WebMapServiceProxy.as_view(),
        name="wms-operation",
    ),
    path(
        "mrmap-proxy/wfs/<pk>",
        WebFeatureServiceProxy.as_view(),
        name="wfs-operation",

    ),
    path(
        "mrmap-proxy/ows/<pk>",
        OwsContextView.as_view(),
        name="ows-context-detail"
    ),
    path('api/auth/login', LoginView.as_view()),
    path('api/auth/logout', LogoutView.as_view()),

    path(
        "csw",
        CswServiceView.as_view(),
        name="csw-endpoint"
    )

]

if settings.DEBUG:
    import debug_toolbar
    from django.conf import settings
    from django.conf.urls.static import static

    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))
    # to enable possibility to open media files during development (images, documents, etc)
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
