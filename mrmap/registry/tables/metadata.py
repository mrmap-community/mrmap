import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from extras.tables.tables import SecuredTable
from extras.tables.template_code import DEFAULT_ACTION_BUTTONS
from registry.models import DatasetMetadata
from registry.tables.conformity import ConformityCheckRunExtraFieldsTable
from registry.tables.template_codes import METADATA_DETAIL_ICONS, VALUE_TABLE_VIEW_LINK


class MetadataTable(SecuredTable):
    perm_checker = None
    details = tables.TemplateColumn(template_code=METADATA_DETAIL_ICONS,
                                    orderable=False,
                                    verbose_name=_("Details"))
    described_object = tables.TemplateColumn(template_code=VALUE_TABLE_VIEW_LINK)
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})


class DatasetMetadataTable(SecuredTable, ConformityCheckRunExtraFieldsTable):
    perm_checker = None
    details = tables.TemplateColumn(template_code=METADATA_DETAIL_ICONS,
                                    verbose_name=_("Details"),
                                    orderable=False)
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = DatasetMetadata
        fields = ("title",
                  "details",
                  "linked_layer_count",
                  "linked_feature_type_count",
                  "linked_service_count")
        prefix = 'dataset-metadata-table'

    @staticmethod
    def render_linked_layer_count(record, value):
        link = f'<a href="{reverse("registry:layer_list")}?id__in='
        for layer in record.self_pointing_layers.all():
            link += f'{layer.pk  },'
        link += f'">{value}</a>'
        return format_html(link)

    @staticmethod
    def render_linked_feature_type_count(record, value):
        link = f'<a href="{reverse("registry:feature_type_list")}?id__in='
        for feature_type in record.self_pointing_feature_types.all():
            link += f'{feature_type.pk  },'
        link += f'">{value}</a>'
        return format_html(link)

    @staticmethod
    def render_linked_service_count(self, record, value):
        link = f'<a href="{reverse("registry:service_csw_list")}?id__in='
        for service in record.self_pointing_services.all():
            link += f'{service.pk  },'
        link += f'">{value}</a>'
        return format_html(link)