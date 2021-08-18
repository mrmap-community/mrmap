import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from django_bootstrap_swt.components import Link

from main.tables.tables import SecuredTable
from main.tables.template_code import DEFAULT_ACTION_BUTTONS, VALUE_ABSOLUTE_LINK
from quality.models import ConformityCheckRun

class ConformityCheckRunTable(SecuredTable):
    perm_checker = None
    resource = tables.columns.TemplateColumn(VALUE_ABSOLUTE_LINK)
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = ConformityCheckRun
        fields = ('config', 'resource', 'resource_type', 'passed', 'report', 'created_at', 'owned_by_org')
        prefix = 'conformity_check_run-table'

    def render_report(self, record):
        return Link(url=record.get_report_url(), content='Validation report').render(safe=True)
