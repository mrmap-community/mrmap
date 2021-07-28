import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from main.tables.tables import SecuredTable
from main.tables.template_code import DEFAULT_ACTION_BUTTONS
from quality.models import ConformityCheckRun


class ConformityCheckRunTable(SecuredTable):
    perm_checker = None
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = ConformityCheckRun
        fields = ('metadata', 'passed', 'created_at', 'created_by_user', 'owned_by_org')
        prefix = 'conformity_check_run-table'
