import uuid
from enum import Enum

from django.contrib.gis.geos import Polygon
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils.html import format_html
from MrMap.consts import BTN_SM_CLASS
from structure.permissionEnums import PermissionEnum


class ModalSizeEnum(Enum):
    LARGE = "modal-lg"
    SMALL = "modal-sm"


class ProgressBar:
    def __init__(self, progress: int = 0, color: str = '', animated: bool = True, striped: bool = True):
        self.progress = progress
        self.color = color
        self.animated = animated
        self.striped = striped

    def render(self) -> str:
        return render_to_string(template_name="skeletons/progressbar.html",
                                context=self.__dict__)


class Badge:
    def __init__(self, name: str, value: str, badge_color: str, badge_pill: bool = False, tooltip: str = '', tooltip_placement: str = 'left',):
        self.name = name
        self.value = value
        self.badge_color = badge_color
        self.badge_pill = badge_pill
        self.tooltip = tooltip
        self.tooltip_placement = tooltip_placement

    def render(self) -> str:
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
        self.value = icon
        self.tooltip = tooltip
        self.tooltip_placement = tooltip_placement
        self.color = color

    def render(self) -> str:
        return render_to_string(template_name="skeletons/icon.html",
                                context=self.__dict__)


class Link:
    def __init__(self, name: str, url: str, value: str, color: str = '', needs_perm: PermissionEnum = None, tooltip: str = None, tooltip_placement: str = 'left', open_in_new_tab: bool = False):
        self.name = name
        self.url = url
        self.value = value
        self.color = color
        self.tooltip = tooltip
        self.tooltip_placement = tooltip_placement
        self.needs_perm = needs_perm
        self.open_in_new_tab = open_in_new_tab

    def render(self) -> str:
        return render_to_string(template_name="sceletons/open-link.html",
                                context=self.__dict__)


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

    def render(self) -> str:
        return render_to_string(template_name="skeletons/open_link_button.html", context=self.__dict__)


class Modal:
    def __init__(self, title: str, modal_body: str, btn_value: str, btn_tooltip: str = None, modal_footer: str = None, fade: bool = True,
                 size: ModalSizeEnum = None, fetch_url: str = None):
        self.title = title
        self.modal_body = modal_body
        self.modal_footer = modal_footer
        self.fade = fade
        self.size = size
        self.modal_id = str(uuid.uuid4())
        self.fetch_url = fetch_url
        self.button = Button(value=btn_value, data_toggle='modal', data_target=f'#id_modal_{self.modal_id}',
                             tooltip=btn_tooltip).render()

    def render(self) -> str:
        return render_to_string(template_name="skeletons/modal_ajax.html" if self.fetch_url else "skeletons/modal.html",
                                context=self.__dict__)


class Accordion:
    def __init__(self, accordion_title: str, accordion_title_center: str = '', accordion_title_right: str = '', accordion_body: str = None, button_type: str = None, fetch_url: str = None):
        self.accordion_title = accordion_title
        self.accordion_title_center = accordion_title_center
        self.accordion_title_right = accordion_title_right
        self.accordion_body = accordion_body
        self.button_type = button_type
        self.fetch_url = fetch_url
        self.accordion_id = str(uuid.uuid4())

    def render(self) -> str:
        return render_to_string(template_name='skeletons/accordion_ajax.html' if self.fetch_url else 'skeletons/accordion.html', context=self.__dict__)


class Button:
    def __init__(self, value: str, color: str = 'btn-info', data_toggle: str = None, data_target: str = None,
                 aria_expanded: str = None, aria_controls: str = None, tooltip: str = None):
        self.value = value
        self.color = color
        self.data_toggle = data_toggle
        self.data_target = data_target
        self.aria_expanded = aria_expanded
        self.aria_controls = aria_controls
        self.tooltip = tooltip

    def render(self) -> str:
        return render_to_string(template_name='skeletons/button.html', context=self.__dict__)


class Collapsible:
    def __init__(self, card_body: str, btn_value: str, collapsible_id: str = None):
        self.card_body = card_body
        self.collapsible_id = collapsible_id if collapsible_id else str(uuid.uuid4())
        self.button = Button(value=btn_value, data_toggle='collapse', data_target=f'#{self.collapsible_id}',
                             aria_expanded='false', aria_controls=self.collapsible_id).render()

    def render(self) -> str:
        return render_to_string(template_name='skeletons/collapsible.html', context=self.__dict__)


class LeafletClient:
    def __init__(self, polygon: Polygon, add_polygon_as_layer: bool = True, height: str = '50vh', min_height: str = '200px'):
        self.polygon = polygon
        self.add_polygon_as_layer = add_polygon_as_layer
        self.height = height
        self.min_height = min_height
        self.map_id = str(uuid.uuid4()).replace("-", "_")

    def render(self) -> str:
        return render_to_string(template_name='skeletons/leaflet_client.html', context=self.__dict__)


class Bootstrap4Helper:

    def __init__(self, request: HttpRequest, add_current_view_params: bool = True):
        self.permission_lookup = {}
        self.request = request
        self.add_current_view_params = add_current_view_params

        self.url_querystring = ''
        if add_current_view_params:
            current_view = self.request.GET.get('current-view', self.request.resolver_match.view_name)
            if self.request.resolver_match.kwargs:
                # if kwargs are not empty, this is a detail view
                if 'pk' in self.request.resolver_match.kwargs:
                    current_view_arg = self.request.resolver_match.kwargs['pk']
                else:
                    current_view_arg = self.request.resolver_match.kwargs['slug']
                current_view_arg = self.request.GET.get('current-view-arg', current_view_arg)
                self.url_querystring = f'?current-view={current_view}&current-view-arg={current_view_arg}'
            else:
                self.url_querystring = f'?current-view={current_view}'

    def check_render_permission(self, permission: PermissionEnum) -> bool:
        has_perm = self.permission_lookup.get(permission, None)
        if has_perm is None:
            has_perm = self.request.user.has_permission(permission)
            self.permission_lookup[permission] = has_perm
        return has_perm

    def render_item(self, item, ignore_current_view_params: bool = False) -> str:
        rendered_string = ''
        has_perm = self.check_render_permission(item.needs_perm) if hasattr(item, 'needs_perm') else True
        if has_perm:
            if self.add_current_view_params and hasattr(item, 'url') and not ignore_current_view_params:
                item.url += self.url_querystring
            rendered_string = item.render()
        return rendered_string

    def render_list_coherent(self, items: [], ignore_current_view_params: bool = False) -> str:
        rendered_string = ''
        for item in items:
            rendered_string += self.render_item(item=item, ignore_current_view_params=ignore_current_view_params)
        return format_html(rendered_string)
