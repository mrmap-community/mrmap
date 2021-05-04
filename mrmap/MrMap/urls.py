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
    path('admin/', admin.site.urls),
    path('', include('users.urls')),
    path('structure/', include('structure.urls')),
    path('acl/', include('acl.urls')),
    path('ac/', include('autocompletes.urls')),
    path('resource/', include('service.urls')),
    path('monitoring/', include('monitoring.urls')),
    path('editor/', include('editor.urls')),
    path('captcha/', include('captcha.urls')),
    path("i18n/", include("django.conf.urls.i18n")),
    path('api/', include('api.urls')),
    path('csw/', include('csw.urls')),
    path('quality/', include('quality.urls')),
]

if DEBUG:
    import debug_toolbar
    urlpatterns.append(
        path('__debug__/', include(debug_toolbar.urls))
    )
