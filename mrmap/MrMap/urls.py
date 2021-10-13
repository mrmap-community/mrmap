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
from django.views.generic.base import RedirectView
from rest_framework.routers import DefaultRouter
from MrMap.settings import DEBUG

# Define a router for our REST API
rest_api_router = DefaultRouter()
# Register REST API routes
# e.g.
# rest_api_router.registry.extend(mapcontext_router.registry) -> mapcontext_router imported from mapcontext urls

urlpatterns = [
    # generic redirect if no path is used
    path('', RedirectView.as_view(url='users/dashboard')),

    # MrMapApps
    path('users/', include('users.urls')),
    path('acls/', include('acls.urls')),
    path('registry/', include('registry.urls')),
    path('jobs/', include('jobs.urls')),

    # captcha support
    path('captcha/', include('captcha.urls')),

    # translation support
    path('i18n/', include("django.conf.urls.i18n")),

    # Autocompletes
    path('ac/registry/', include('registry.autocompletes.urls')),
    path('ac/users/', include('users.autocompletes.urls')),

    # REST API
    path(r'api/v1/', include((rest_api_router.urls, 'rest_framework'), namespace='api')),
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
