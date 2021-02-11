from MrMap.settings import GIT_REPO_URI, GIT_GRAPH_URI
from MrMap.sub_settings.dev_settings import ROOT_URL
from MrMap.utils import get_theme


def default_context(request):
    if request.user is not None and not request.user.is_anonymous:
        permissions = request.user.get_permissions()
    else:
        permissions = []

    return {
        "ROOT_URL": ROOT_URL,
        "PATH": request.path.split("/")[1],
        "FULL_PATH": request.path,
        "LANGUAGE_CODE": request.LANGUAGE_CODE,
        "user_permissions": permissions,
        "GIT_REPO_URI": GIT_REPO_URI,
        "GIT_GRAPH_URI": GIT_GRAPH_URI,
        "THEME": get_theme(request.user),
    }
