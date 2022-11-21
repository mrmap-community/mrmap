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

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.cache import cache_page
from extras.openapi import CustomSchemaGenerator
from registry.proxy.wfs_proxy import WebFeatureServiceProxy
from registry.proxy.wms_proxy import WebMapServiceProxy
from registry.views_ows.mapcontext import OwsContextView
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

urlpatterns = [
    path("django-admin/", admin.site.urls),
    # captcha support
    path("captcha/", include("captcha.urls")),
    # translation support
    path("i18n/", include("django.conf.urls.i18n")),
    # REST API
    # registry api urls
    path("api/v1/registry/", include("registry.urls", namespace="registry")),
    path("api/v1/accounts/", include("accounts.urls", namespace="accounts")),
    path("api/v1/notify/", include("notify.urls", namespace="notify")),
    path(
        "api/schema/",
        cache_page(timeout=60 * 15, cache="local-memory")(
            get_schema_view(
                title="MrMap JSON:API",
                description="API for all things …",
                version="1.0.0",
                public=True,
                generator_class=CustomSchemaGenerator,
                renderer_classes=[JSONOpenAPIRenderer]
            )
        ),
        name="openapi-schema",
    ),
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
]

if settings.DEBUG:
    import debug_toolbar
    from django.conf import settings
    from django.conf.urls.static import static

    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))
    # to enable possibility to open media files during development (images, documents, etc)
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
