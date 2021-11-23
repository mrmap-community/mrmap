"""MrMap URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='users:dashboard')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='users:dashboard')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path, include
from MrMap.settings import DEBUG
from django.views.generic import TemplateView
from rest_framework.schemas import get_schema_view
from rest_framework_json_api.schemas.openapi import SchemaGenerator
from django.views.decorators.cache import cache_page


urlpatterns = [

    # captcha support
    path('captcha/', include('captcha.urls')),

    # translation support
    path('i18n/', include("django.conf.urls.i18n")),

    # REST API

    # registry api urls
    path('api/v1/registry/', include('registry.api.urls', namespace='registry')),
    path('api/v1/users/', include('users.api.urls', namespace='users')),
    # path('api/v1/auth/', include('dj_rest_auth.urls')),

    path(
        "api/schema/",
        cache_page(timeout=60 * 15, cache='local-memory')(
            get_schema_view(
                title="MrMap JSON:API",
                description="API for all things …",
                version="1.0.0",
                generator_class=SchemaGenerator,
            )
        ),
        name="openapi-schema",
    ),
    path(
        "api/schema/swagger-ui/",
        TemplateView.as_view(
            template_name="extras/swagger-ui.html",
            extra_context={"schema_url": "openapi-schema"},
        ),
        name="swagger-ui",
    ),
]

if DEBUG:
    import debug_toolbar
    from django.conf import settings
    from django.conf.urls.static import static

    urlpatterns.append(
        path('__debug__/', include(debug_toolbar.urls))
    )
    # to enable possibility to open media files during development (images, documents, etc)
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
