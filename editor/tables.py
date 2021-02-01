from django.db.models import Q
from django.forms import fields
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django_bootstrap_swt.components import Link, Tag, Modal, Accordion
from django_bootstrap_swt.enums import ButtonColorEnum, ModalSizeEnum
import django_tables2 as tables
from leaflet.forms.fields import GeometryField
from leaflet.forms.widgets import LeafletWidget

from MrMap.columns import MrMapColumn
from MrMap.icons import IconEnum
from django.utils.translation import gettext_lazy as _
from MrMap.utils import get_ok_nok_icon
from service.models import Metadata, AllowedOperation
from structure.models import MrMapGroup
from structure.permissionEnums import PermissionEnum


class AllowedOperationTable(tables.Table):
    class Meta:
        model = AllowedOperation
        fields = ('operations', 'allowed_groups', 'root_metadata', 'allowed_area')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'allowed-operations-table'

    def render_allowed_area(self, record, value):
        leaflet_widget = LeafletWidget()
        leaflet_widget.modifiable = False
        leaflet_field = GeometryField(widget=leaflet_widget)
        field_name = f'id-{record.id}-allowed_area'
        field_value = value.geojson
        leaflet_field_html = leaflet_field.widget.render(field_name, field_value)
        # todo: nest the leaflet client in a accordion. We need to customize the init call to the shown event of the
        #  accordion
        return mark_safe(leaflet_field_html)


class EditorAcessTable(tables.Table):
    access_allowed = tables.Column(
        accessor='allowed_operations',
        verbose_name=_('Access allowed'),
    )

    access_restricted_spatially = tables.Column(
        accessor='allowed_operations',
        verbose_name=_('Access restricted spatially'),
    )

    actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=_('Actions you can perform'),
        attrs={"td": {"style": "white-space:nowrap;"}})

    class Meta:
        model = MrMapGroup
        fields = ('name', 'organization', 'access_allowed', 'access_restricted_spatially', 'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'acces-group-table'

    def __init__(self,
                 related_metadata: Metadata,
                 *args,
                 **kwargs):
        self.related_metadata = related_metadata
        super(EditorAcessTable, self).__init__(*args, **kwargs)

    def render_name(self, record):
        url = reverse('structure:detail-group', args=(record.id,))
        icon = ''
        tooltip = _('Click to open the detail view of <strong>{}</strong>'.format(record.name))
        if record.is_public_group:
            icon = Tag(tag='i', attrs={"class": [IconEnum.PUBLIC.value]}).render()
            tooltip = _('This is the anonymous public user group.') + " {}".format(tooltip)
        return Link(tooltip=tooltip,
                    url=url,
                    content=format_html("{} {}".format(icon, record.name)),
                    needs_perm=None,
                    open_in_new_tab=True, ).render(safe=True)

    def render_organization(self, record):
        if record.organization:
            url = reverse('structure:detail-organization', args=(record.organization.id,))
            tooltip = _('Click to open the detail view of <strong>{}</strong>.'.format(record.organization.organization_name))
            return Link(tooltip=tooltip,
                        url=url,
                        content=record.organization.organization_name,
                        open_in_new_tab=True).render(safe=True)
        else:
            return '-'

    def render_access_allowed(self, value):
        if value.filter(secured_metadata=self.related_metadata).exists():
            return get_ok_nok_icon(True)
        else:
            return get_ok_nok_icon(False)

    def render_access_restricted_spatially(self, value):
        is_restricted_spatially = ~Q(allowed_area=None)
        is_equal_secured_metadata = Q(secured_metadata=self.related_metadata)
        if value.filter(is_equal_secured_metadata & is_restricted_spatially).exists():
            return get_ok_nok_icon(True)
        else:
            return get_ok_nok_icon(False)

    def render_actions(self, record):
        return Modal(
            fetch_url=reverse('editor:restrict-access-spatially', args=(self.related_metadata.id, record.id,)),
            btn_attrs={"class": [ButtonColorEnum.INFO.value]},
            btn_content=Tag(tag='i', attrs={"class": [IconEnum.EDIT.value]}).render(),
            size=ModalSizeEnum.LARGE,
            needs_perm=PermissionEnum.CAN_EDIT_METADATA,
            btn_tooltip=format_html(_(f"Edit access for group <strong>{record.name}</strong>"), )
        ).render(safe=True)
