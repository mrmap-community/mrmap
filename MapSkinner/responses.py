"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from django.http import JsonResponse, HttpRequest

from MapSkinner.settings import ROOT_URL, VERSION, GIT_REPO_URI
from structure.models import User
from MapSkinner.utils import get_theme

class DefaultContext:
    """ Contains the default values that have to be set on every rendering process!

    """

    def __init__(self, request: HttpRequest, context: dict, user: User = None):
        if user is not None:
            permissions = user.get_permissions()
        else:
            permissions = []
        self.context = {
            "ROOT_URL": ROOT_URL,
            "PATH": request.path.split("/")[1],
            "LANGUAGE_CODE": request.LANGUAGE_CODE,
            "user_permissions": permissions,  #user_helper.get_permissions(user)
            "user": user,
            "VERSION": VERSION,
            "GIT_REPO_URI": GIT_REPO_URI,
            "THEME": get_theme(user),
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
