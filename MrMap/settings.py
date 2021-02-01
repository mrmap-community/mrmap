"""
Django settings for MrMap project.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

# Include other settings files (DO NOT TOUCH THESE!)
from MrMap.sub_settings.django_settings import *
from MrMap.sub_settings.dev_settings import *
from MrMap.sub_settings.db_settings import *
from MrMap.sub_settings.logging_settings import *
from api.settings import REST_FRAMEWORK

ALLOWED_HOSTS = [
    HOST_NAME,
    "127.0.0.1",
]

# GIT repo links
GIT_REPO_URI = "https://git.osgeo.org/gitea/GDI-RP/MrMap/src/branch/pre_master"
GIT_GRAPH_URI = "https://git.osgeo.org/gitea/GDI-RP/MrMap/graph"

LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
LOGIN_URL = "login"

# Defines the semantic web information which will be injected on the resource html views
SEMANTIC_WEB_HTML_INFORMATION = {
    "legalName": "Zentrale Stelle GDI-RP",
    "email": "kontakt@geoportal.rlp.de",
    "addressCountry": "DE",
    "streetAddress": "Von-Kuhl-Straße 49",
    "addressRegion": "RLP",
    "postalCode": "56070",
    "addressLocality": "Koblenz",
}

# Defines the timespan for fetching the last activities on dashboard
LAST_ACTIVITY_DATE_RANGE = 7

# configure your proxy like "http://10.0.0.1:8080"
# or with username and password: "http://username:password@10.0.0.1:8080"
HTTP_PROXY = ""
PROXIES = {
    "http": HTTP_PROXY,
    "https": HTTP_PROXY,
}