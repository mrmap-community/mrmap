"""MrMap URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from MrMap.settings import DEBUG

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Apps
    path('', include('users.urls')),
    path('structure/', include('structure.urls')),
    path('acls/', include('acls.urls')),
    path('ac-old/', include('autocompletes.urls')),
    path('registry/', include('registry.urls')),
    path('monitoring/', include('monitoring.urls')),
    path('captcha/', include('captcha.urls')),
    path("i18n/", include("django.conf.urls.i18n")),
    path('csw/', include('csw.urls')),
    path('quality/', include('quality.urls')),
    path('job/', include('job.urls')),

    # Autocompletes
    path('ac/registry/', include('registry.autocompletes.urls')),
    path('ac/users/', include('users.autocompletes.urls')),
]

if DEBUG:
    import debug_toolbar
    urlpatterns.append(
        path('__debug__/', include(debug_toolbar.urls))
    )
