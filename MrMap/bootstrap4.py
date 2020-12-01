from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils.html import format_html

from MrMap.consts import BTN_SM_CLASS
from MrMap.utils import get_theme
from structure.permissionEnums import PermissionEnum
from django.utils.translation import gettext_lazy as _


class Badge:
    def __init__(self, name: str, value: str, badge_color: str, badge_pill: bool = False, tooltip: str = '', tooltip_placement: str = 'left',):
        self.name = name
        self.value = value
        self.badge_color = badge_color
        self.badge_pill = badge_pill
        self.tooltip = tooltip
        self.tooltip_placement = tooltip_placement

    def render(self):
        context = {
            "badge_color": self.badge_color,
            "badge_pill": self.badge_pill,
            "value": self.value,
            "tooltip": self.tooltip,
            "tooltip_placement": self.tooltip_placement,
            }
        return render_to_string(template_name="sceletons/badge_with_tooltip.html",
                                context=context)


class Icon:
    def __init__(self, name: str, icon: str, tooltip: str = None, tooltip_placement: str = 'left', color: str = ''):
        self.name = name
        self.icon = icon
        self.tooltip = tooltip
        self.tooltip_placement = tooltip_placement
        self.color = color

    def render(self):
        context = {
            "icon_color": self.color,
            "icon": self.icon,
            "tooltip": self.tooltip,
            "tooltip_placement": self.tooltip_placement,
        }
        return render_to_string(template_name="sceletons/icon_with_tooltip.html",
                                context=context)


class LinkButton:
    def __init__(self, name: str, url: str, value: str, color: str, needs_perm: PermissionEnum = None, tooltip: str = None, tooltip_placement: str = 'left', size: str = BTN_SM_CLASS):
        self.name = name
        self.url = url
        self.value = value
        self.color = color
        self.tooltip = tooltip
        self.tooltip_placement = tooltip_placement
        self.needs_perm = needs_perm
        self.size = size

    def render(self):
        context = {
            "btn_size": self.size,
            "btn_color": self.color,
            "btn_value": self.value,
            "btn_url": self.url,
            "tooltip": self.tooltip,
            "tooltip_placement": self.tooltip_placement,
        }
        return render_to_string(template_name="sceletons/open-link-button.html",
                                context=context)


class Bootstrap4Helper:

    def __init__(self, request: HttpRequest, add_current_view_params: bool = True):
        self.permission_lookup = {}
        self.request = request
        self.add_current_view_params = add_current_view_params

        self.url_querystring = ''
        if add_current_view_params:
            current_view = self.request.GET.get('current-view', self.request.resolver_match.view_name)
            current_view_arg = self.request.GET.get('current-view-arg', '')
            if current_view_arg:
                self.url_querystring = f'?current-view={current_view}&current-view-arg={current_view_arg}'
            else:
                self.url_querystring = f'?current-view={current_view}'

    def check_render_permission(self, permission: PermissionEnum):
        has_perm = self.permission_lookup.get(permission, None)
        if has_perm is None:
            has_perm = self.request.user.has_permission(permission)
            self.permission_lookup[permission] = has_perm
        return has_perm

    # deprecated
    def get_link(self, href: str, value: str, permission: PermissionEnum = None, tooltip_placement: str = 'left',
                 open_in_new_tab: bool = False, tooltip: str = None, ):
        has_perm = self.check_render_permission(permission)
        if has_perm:
            context = {
                "href": href + self.url_querystring if self.add_current_view_params else href,
                "value": value,
                "link_color": get_theme(self.request.user)["TABLE"]["LINK_COLOR"],
                "tooltip": tooltip,
                "tooltip_placement": tooltip_placement,
                "new_tab": open_in_new_tab,
            }
            return format_html(render_to_string(template_name="sceletons/open-link.html",
                                                context=context))
        else:
            return ''

    # deprecated
    def get_btn(self, href: str, btn_color: str, btn_value: str, permission: PermissionEnum = None, tooltip: str = '', tooltip_placement: str = 'left',):
        has_perm = self.check_render_permission(permission)
        if has_perm:
            context = {
                "btn_size": BTN_SM_CLASS,
                "btn_color": btn_color,
                "btn_value": btn_value,
                "btn_url": href + self.url_querystring if self.add_current_view_params else href,
                "tooltip": tooltip,
                "tooltip_placement": tooltip_placement,
            }
            return render_to_string(template_name="sceletons/open-link-button.html",
                                    context=context)
        else:
            return ''

    def render_list_coherent(self, items: []):
        rendered_string = ''
        for item in items:
            has_perm = self.check_render_permission(item.needs_perm) if hasattr(item, 'needs_perm') else True
            if has_perm:
                rendered_string += item.render()
        return rendered_string

    # deprecated
    @staticmethod
    def get_icon(icon: str, icon_color: str = None, tooltip: str = '', tooltip_placement: str = 'left', ):
        context = {
            "icon_color": icon_color,
            "icon": icon,
            "tooltip": tooltip,
            "tooltip_placement": tooltip_placement,
        }
        return render_to_string(template_name="sceletons/icon_with_tooltip.html",
                                context=context)