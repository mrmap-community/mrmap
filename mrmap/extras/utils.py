import collections.abc
import re
import urllib.parse as urlparse

from rest_framework.renderers import BrowsableAPIRenderer


def update_url_query_params(url: str, params: dict):
    url_parse = urlparse.urlparse(url)
    query = url_parse.query
    url_dict = dict(urlparse.parse_qsl(query))
    url_dict.update(params)
    url_new_query = urlparse.urlencode(url_dict)
    url_parse = url_parse._replace(query=url_new_query)
    return urlparse.urlunparse(url_parse)


def update_url_base(url: str, base: str):
    old = urlparse.urlparse(url)
    new = urlparse.urlparse(base)
    old._replace(scheme=new.scheme, path=new.path)
    return urlparse.urlunparse(old)


def execute_threads(thread_list):
    """Executes a list of threads

    Args:
        thread_list (list): A list of threads
    Returns: nothing
    """
    for thread in thread_list:
        thread.start()
    for thread in thread_list:
        thread.join()


class BrowsableAPIRendererWithoutForms(BrowsableAPIRenderer):
    """Renders the browsable api, but excludes the forms."""

    def get_context(self, *args, **kwargs):
        ctx = super().get_context(*args, **kwargs)
        ctx["display_edit_forms"] = False
        return ctx

    def show_form_for_method(self, view, method, request, obj):
        """We never want to do this! So just return False."""
        return False

    def get_rendered_html_form(self, data, view, method, request):
        """Why render _any_ forms at all. This method should return
        rendered HTML, so let's simply return an empty string.
        """
        return ""
