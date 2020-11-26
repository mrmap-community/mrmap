from django.template.loader import render_to_string

from MrMap.consts import BTN_SM_CLASS
from MrMap.utils import get_theme
from structure.models import MrMapUser
from structure.permissionEnums import PermissionEnum


class Bootstrap4Helper:

    def __init__(self, user: MrMapUser):
        self.permission_lookup = {}
        self.user = user

    def check_render_permission(self, permission: PermissionEnum):
        has_perm = self.permission_lookup.get(permission, None)
        if has_perm is None:
            has_perm = self.user.has_permission(permission)
            self.permission_lookup[permission] = has_perm
        return has_perm

    def get_link(self, href: str, value: str, permission: PermissionEnum, tooltip_placement: str = 'left',
                 open_in_new_tab: bool = False, tooltip: str = None, ):
        has_perm = self.check_render_permission(permission)
        if has_perm:
            context = {
                "href": href,
                "value": value,
                "link_color": get_theme(self.user)["TABLE"]["LINK_COLOR"],
                "tooltip": tooltip,
                "tooltip_placement": tooltip_placement,
                "new_tab": open_in_new_tab,
            }
            return render_to_string(template_name="sceletons/open-link.html",
                                    context=context)
        else:
            return ''

    def get_btn(self, href: str, btn_color: str, btn_value: str, permission: PermissionEnum = None, tooltip: str = '', tooltip_placement: str = 'left',):
        has_perm = self.check_render_permission(permission)
        if has_perm:
            context = {
                "btn_size": BTN_SM_CLASS,
                "btn_color": btn_color,
                "btn_value": btn_value,
                "btn_url": href,
                "tooltip": tooltip,
                "tooltip_placement": tooltip_placement,
            }
            return render_to_string(template_name="sceletons/open-link-button.html",
                                    context=context)
        else:
            return ''

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