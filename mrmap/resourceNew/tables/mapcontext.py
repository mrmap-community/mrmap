import django_tables2 as tables
from resourceNew.models.mapcontext import MapContext
from django.utils.translation import gettext_lazy as _
from resourceNew.tables.template_codes import MAP_CONTEXT_TABLE_ACTIONS


# TODO
class MapContextTable(tables.Table):

    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=MAP_CONTEXT_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}})

    class Meta:
        model = MapContext
        fields = ('title', 'abstract', 'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'map-context-table'