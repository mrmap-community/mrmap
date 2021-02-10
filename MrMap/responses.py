"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from collections import OrderedDict

from django.http import JsonResponse, HttpRequest
from django.urls import resolve, Resolver404, get_resolver

from MrMap.settings import ROOT_URL, GIT_REPO_URI, GIT_GRAPH_URI
from structure.models import MrMapUser
from MrMap.utils import get_theme


def check_path_exists(path):
    try:
        match = resolve(path=path)
        return match
    except Resolver404:
        return None


class BreadCrumbItem:
    def __init__(self, path: str,
                 verbose_name: str = None,
                 is_representative: bool = True,
                 is_specific: bool = False,
                 is_active_path: bool = False,
                 children=None,
                 parent=None):
        self.path = path
        self.verbose_name = verbose_name
        self.is_representative = is_representative
        self.is_specific = is_specific
        self.is_active_path = is_active_path
        self.children = children
        self.parent = parent


class ChildPathResolver:
    children = None

    def __init__(self, breadcrumb_item: BreadCrumbItem):
        root_path_match = check_path_exists(path=breadcrumb_item.path)
        if root_path_match and breadcrumb_item.is_specific:
            url_resolver = get_resolver(root_path_match.app_name + '.urls')
            for pattern in url_resolver.url_patterns:
                route_under_test = root_path_match.namespace + '/' + pattern.pattern.__str__()
                match_route_length = len(root_path_match.route.split("/"))
                route_length = len(route_under_test.split("/"))
                if root_path_match.route in route_under_test and \
                        root_path_match.route != route_under_test and \
                        route_length <= match_route_length + 1:
                    route_under_test = f"{breadcrumb_item.path}/{route_under_test.split('/')[-1]}"
                    child_match = check_path_exists(path=route_under_test)
                    if child_match:
                        if not self.children:
                            self.children = OrderedDict()
                        self.children[child_match.url_name] = BreadCrumbItem(path=f"{breadcrumb_item.path}/{route_under_test.split('/')[-1]}",
                                                                             verbose_name=child_match.url_name,
                                                                             is_representative=True)

    @property
    def has_children(self):
        return True if self.children else False


class ParentPathResolver:
    parent = None

    def __init__(self, breadcrumb_item: BreadCrumbItem):
        child_path_match = check_path_exists(path=breadcrumb_item.path)
        if child_path_match:
            parent_path = breadcrumb_item.path.rsplit('/', 1)[0]
            parent_path_match = check_path_exists(path=parent_path)
            if parent_path_match:
                is_specific = True if 'pk' in parent_path_match.kwargs and 'pk' in parent_path_match.route.split("/")[-1] else False
                self.parent = BreadCrumbItem(is_representative=True,
                                             verbose_name=parent_path_match.url_name,
                                             path=parent_path,
                                             is_specific=is_specific,
                                             is_active_path=True)
            else:
                self.parent = BreadCrumbItem(is_representative=False,
                                             path=parent_path,
                                             is_active_path=True)
            child_path_resolver = ChildPathResolver(breadcrumb_item=self.parent)
            self.parent.children = child_path_resolver.children
            if self.has_parent:
                self.parent.parent = ParentPathResolver(breadcrumb_item=self.parent).parent

    @property
    def has_parent(self):
        return True if check_path_exists(path=self.parent.path) else False


class BreadCrumbBuilder:
    breadcrumb = None

    def __init__(self, path: str):
        self.path = path

    def build_breadcrumb(self):
        path_items = self.path.split("/")
        path_items.pop(0)
        path_tmp = ""

        self.breadcrumb = OrderedDict()
        for path_item in path_items:
            path_tmp += "/" + path_item
            match = check_path_exists(path_tmp)
            if match:
                is_specific = True if 'pk' in match.kwargs and 'pk' in match.route.split("/")[-1] else False
                is_active_path = True if self.path == path_tmp else False
                breadcrumb_item = BreadCrumbItem(is_representative=True,
                                                 verbose_name=match.url_name,
                                                 path=path_tmp,
                                                 is_specific=is_specific,
                                                 is_active_path=is_active_path)
                child_path_resolver = ChildPathResolver(breadcrumb_item=breadcrumb_item)
                parent_path_resolver = ParentPathResolver(breadcrumb_item=breadcrumb_item)
                breadcrumb_item.children = child_path_resolver.children if child_path_resolver.has_children else None
                breadcrumb_item.parent = parent_path_resolver.parent
                self.breadcrumb[path_item] = breadcrumb_item.__dict__
            else:
                self.breadcrumb[path_item] = BreadCrumbItem(is_representative=False,
                                                            path=path_tmp).__dict__
        return self.breadcrumb


class DefaultContext:
    """ Contains the default values that have to be set on every rendering process!

    """

    def __init__(self, request: HttpRequest, context: dict, user: MrMapUser = None):
        if user is not None and not user.is_anonymous:
            permissions = user.get_permissions()
        else:
            permissions = []

        self.context = {
            "ROOT_URL": ROOT_URL,
            "PATH": request.path.split("/")[1],
            "FULL_PATH": request.path,
            "LANGUAGE_CODE": request.LANGUAGE_CODE,
            "user_permissions": permissions,  # user_helper.get_permissions(user)
            "user": user,
            "GIT_REPO_URI": GIT_REPO_URI,
            "GIT_GRAPH_URI": GIT_GRAPH_URI,
            "THEME": get_theme(user),
            "BREADCRUMB_CONFIG": BreadCrumbBuilder(path=request.path).build_breadcrumb(),
        }
        self.add_context(context)

    def get_context(self):
        """ Returns the context dict

        Returns:
             The context dict
        """
        return self.context

    def add_context(self, context: dict):
        """ Adds a complete dict to the default configuration

        Args:
            context (dict): The context dict
        Returns:
        """
        for key, val in context.items():
            self.context[key] = val


class APIResponse:
    def __init__(self):
        self.data = {
            "success": False,
            "msg": "",
        }


class BackendAjaxResponse:
    """ Generic JsonResponse wrapper for Backend->Frontend(AJAX) communication

    Use for AJAX responses.
    There are three default values for the response: 'html', 'response' and 'url'.
    'Html' contains prerendered html content, that will be pasted by Javascript into an html element.

    IMPORTANT:
    Always(!) use this object instead of a direct JsonResponse() object.

    """

    def __init__(self, html, **kwargs: dict):
        self.context = {
            "html": html,
            "ROOT_URL": ROOT_URL,
        }
        # add optional parameters
        for arg_key, arg_val in kwargs.items():
            self.context[arg_key] = arg_val

    def get_response(self):
        """ Return the JsonResponse

        Returns:
             The JsonResponse
        """
        return JsonResponse(self.context)
