"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from django.http import JsonResponse


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
