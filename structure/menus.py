from django.http import HttpRequest
from django.urls import reverse
from menu import MenuItem, Menu
from django.utils.translation import gettext as _


def resolve_url(request: HttpRequest, view_name: str):
    return reverse(view_name, args=[request.resolver_match.kwargs.get('pk'), ])


class CustomMenuItem(MenuItem):

    def process(self, request):
        # evaluate our url
        if callable(self.url):
            self.url = self.url(request, self.view_name)
        super().process(request)


children = (
    CustomMenuItem(_("Edit Group"),
                   resolve_url,
                   weight=10,
                   view_name='structure:group_edit'),
    CustomMenuItem(_("Delete Group"),
                   resolve_url,
                   weight=20,
                   view_name='structure:group_remove',),
    CustomMenuItem(_("Members"),
                   resolve_url,
                   weight=30,
                   view_name='structure:group_members',),
    CustomMenuItem(_("Publishes for"),
                   resolve_url,
                   weight=40,
                   view_name='structure:group_publisher_overview'),
)

Menu.add_item('group_details', CustomMenuItem("Details",
                                              resolve_url,
                                              weight=10,
                                              children=children,
                                              view_name='structure:group_details'))
