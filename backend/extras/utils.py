import re
import urllib.parse as urlparse
from collections import defaultdict

from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework_json_api.utils import \
    get_included_resources as get_included_resources_json_api
from rest_framework_json_api.utils import undo_format_field_name


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


def parse_sparse_fieldsets(request):
    fieldsets = defaultdict(list)
    pattern = re.compile(r"^fields\[(?P<resource>[^\]]+)\]$")
    if request and hasattr(request, "GET"):
        for key, value in request.GET.items():
            match = pattern.match(key)
            if match and value:
                resource = match.group("resource")
                fieldsets[resource] = [undo_format_field_name(v.strip())
                                       for v in value.split(",") if v.strip()]

    return dict(fieldsets)


def get_request(request):
    from simple_history.models import HistoricalRecords

    if not request and hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    if request and not hasattr(request, "query_params"):
        request.query_params = request.GET
    return request


def get_sparse_fields(request=None):
    request = get_request(request)
    return parse_sparse_fieldsets(request)


def get_included_resources(request=None):
    request = get_request(request)
    return get_included_resources_json_api(request)


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
        return ""
        return ""
        return ""
