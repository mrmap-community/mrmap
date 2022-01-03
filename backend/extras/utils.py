import re
import urllib.parse as urlparse

from django.contrib import messages
from django.utils.html import escape
from django.utils.safestring import mark_safe
from rest_framework.renderers import BrowsableAPIRenderer


def camel_to_snake(name):
    name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def handle_protected_error(obj_list, request, e):
    """
    Generate a user-friendly error message in response to a ProtectedError exception.
    """
    protected_objects = list(e.protected_objects)
    protected_count = (
        len(protected_objects) if len(
            protected_objects) <= 50 else "More than 50"
    )
    err_message = (
        f"Unable to delete <strong>{', '.join(str(obj) for obj in obj_list)}</strong>. "
        f"{protected_count} dependent objects were found: "
    )

    # Append dependent objects to error message
    dependent_objects = []
    for dependent in protected_objects[:50]:
        if hasattr(dependent, "get_absolute_url") and dependent.get_absolute_url():
            dependent_objects.append(
                f'<a href="{dependent.get_absolute_url()}">{escape(dependent)}</a>'
            )
        elif (
            hasattr(dependent, "get_concrete_table_url")
            and dependent.get_concrete_table_url()
        ):
            dependent_objects.append(
                f'<a href="{dependent.get_concrete_table_url()}">{escape(dependent)}</a>'
            )
        else:
            dependent_objects.append(str(dependent))
    err_message += ", ".join(dependent_objects)

    messages.error(request, mark_safe(err_message))


def update_url_query_params(url, params):
    url_parse = urlparse.urlparse(url)
    query = url_parse.query
    url_dict = dict(urlparse.parse_qsl(query))
    url_dict.update(params)
    url_new_query = urlparse.urlencode(url_dict)
    url_parse = url_parse._replace(query=url_new_query)
    return urlparse.urlunparse(url_parse)


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
