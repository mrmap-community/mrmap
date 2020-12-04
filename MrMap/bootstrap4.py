from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils.html import format_html

from MrMap.consts import BTN_SM_CLASS
from structure.permissionEnums import PermissionEnum


class ProgressBar:
    def __init__(self, progress: int = 0, color: str = '', animated: bool = True, striped: bool = True):
        self.progress = progress
        self.color = color
        self.animated = animated
        self.striped = striped

    def render(self):
        context = {
            "progress": self.progress,
            "color": self.color,
            "animated": self.animated,
            "striped": self.striped,
        }
        return render_to_string(template_name="skeletons/progressbar.html",
                                context=context)


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


class Link:
    def __init__(self, name: str, url: str, value: str, color: str = '', needs_perm: PermissionEnum = None, tooltip: str = None, tooltip_placement: str = 'left'):
        self.name = name
        self.url = url
        self.value = value
        self.color = color
        self.tooltip = tooltip
        self.tooltip_placement = tooltip_placement
        self.needs_perm = needs_perm

    def render(self):
        context = {
            "color": self.color,
            "value": self.value,
            "url": self.url,
            "tooltip": self.tooltip,
            "tooltip_placement": self.tooltip_placement,
        }
        return render_to_string(template_name="sceletons/open-link.html",
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
            # todo: check if the requested view is a detail view to solve the requested id
            # todo: maybe we can do that by proofing if isinstance(view, DetailView)...
            # todo: for that we first have to refactor the detail views
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

    def render_item(self, item):
        rendered_string = ''
        has_perm = self.check_render_permission(item.needs_perm) if hasattr(item, 'needs_perm') else True
        if has_perm:
            if self.add_current_view_params and hasattr(item, 'url'):
                item.url += self.url_querystring
            rendered_string = item.render()
        return rendered_string

    def render_list_coherent(self, items: []):
        rendered_string = ''
        for item in items:
            rendered_string += self.render_item(item=item)
        return format_html(rendered_string)
