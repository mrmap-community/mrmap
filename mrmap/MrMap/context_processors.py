from django.http import HttpRequest
from django.conf import settings as django_settings
from MrMap.icons import get_all_icons
from django.conf import settings


def default_context(request: HttpRequest):
    context = {
        "PATH": request.path.split("/")[1],
        "FULL_PATH": request.path,
        "LANGUAGE_CODE": request.LANGUAGE_CODE,
        "GIT_REPO_URI": settings.GIT_REPO_URI,
        "GIT_GRAPH_URI": settings.GIT_GRAPH_URI,
        "ICONS": get_all_icons(),
        "settings": django_settings,
    }
    return context
