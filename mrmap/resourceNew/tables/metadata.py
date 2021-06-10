import django_tables2 as tables
from django.urls import reverse

from main.tables.template_code import RECORD_ABSOLUTE_LINK_VALUE_CONTENT
from main.tables.tables import SecuredTable
from resourceNew.models import DatasetMetadata, ServiceMetadata, LayerMetadata, FeatureTypeMetadata
from django.utils.html import format_html


class ServiceMetadataTable(SecuredTable):
    # todo
    """actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})"""

    class Meta:
        model = ServiceMetadata
        fields = ("title",
                  "described_element")


class LayerMetadataTable(SecuredTable):
    # todo
    """actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})"""

    class Meta:
        model = LayerMetadata
        fields = ("title",
                  "described_element")


class FeatureTypeMetadataTable(SecuredTable):
    # todo
    """actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})"""

    class Meta:
        model = FeatureTypeMetadata
        fields = ("title",
                  "described_element")


class DatasetMetadataTable(SecuredTable):
    title = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK_VALUE_CONTENT)

    # todo
    """actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})"""

    class Meta:
        model = DatasetMetadata
        fields = ("title",
                  "linked_layer_count",
                  "linked_feature_type_count")
        prefix = 'dataset-metadata-table'

    def render_linked_layer_count(self, record, value):
        f'<a tabindex="0" data-bs-toggle="popover" data-bs-trigger="focus" title="details" ' \
        f'data-bs-content="content">details</a> '
        link = f'<a href="{reverse("resourceNew:layer_list")}?id__in='
        for layer in record.self_pointing_layers.all():
            link += f'{layer.pk  },'
        link += f'">{value}</a>'
        return format_html(link)

    def render_linked_feature_type_count(self, record, value):
        f'<a tabindex="0" data-bs-toggle="popover" data-bs-trigger="focus" title="details" ' \
        f'data-bs-content="content">details</a> '
        link = f'<a href="{reverse("resourceNew:feature_type_list")}?id__in='
        for feature_type in record.self_pointing_feature_types.all():
            link += f'{feature_type.pk  },'
        link += f'">{value}</a>'
        return format_html(link)
