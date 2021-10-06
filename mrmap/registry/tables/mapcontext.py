import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from extras.tables.tables import SecuredTable
from extras.tables.template_code import DEFAULT_ACTION_BUTTONS
from registry.models.mapcontext import MapContext


class MapContextTable(SecuredTable):
    perm_checker = None
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = MapContext
        fields = ('title', 'abstract', 'actions')
        template_name = "MrMap/skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'map-context-table'
