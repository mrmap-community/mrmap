import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_bootstrap_swt.components import Link

from MrMap.icons import get_icon, IconEnum
from job.enums import TaskStatusEnum
from main.tables.tables import SecuredTable
from main.tables.template_code import DEFAULT_ACTION_BUTTONS
from quality.models import ConformityCheckRun
import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)


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
        fields = ('metadata', 'config', 'passed', 'report', 'created_at', 'created_by_user', 'owned_by_org')
        prefix = 'conformity_check_run-table'

    @staticmethod
    def render_report(record):
        return Link(url=record.get_report_url(), content='Validation report').render(safe=True)


class ConformityCheckRunExtraFieldsTable(tables.Table):
    latest_check = tables.Column(verbose_name=_('Latest check'),
                                 attrs={"th": {"class": "col-sm-1"}},
                                 empty_values=[])

    total_check_count = tables.Column(verbose_name=_('Total check count'),
                                      attrs={"th": {"class": "col-sm-1"}},
                                      empty_values=[])

    class Meta:
        model = ConformityCheckRun
        fields = ["latest_check", "total_check_count"]
        prefix = "conformity_check_run-extra-fields-table"

    @staticmethod
    def render_latest_check(record):
        latest_check = ConformityCheckRun.objects.get_latest_check(record)
        if latest_check:
            latest_check_creation_datetime_str = latest_check.created_at.strftime("%m/%d/%Y %I:%M%p")
            latest_check_passed = latest_check.passed
            if latest_check_passed is True:
                icon = get_icon(IconEnum.OK, 'text-success')
            elif latest_check_passed is False:
                icon = get_icon(IconEnum.NOK, 'text-danger')
            else:
                icon = get_icon(IconEnum.PENDING, 'text-warning')

            link_to_report = reverse('quality:conformity_check_run_report', kwargs={'pk': latest_check.pk})
            content = f'<span>{latest_check_creation_datetime_str} {icon}</span>'
            return Link(url=link_to_report, content=content).render(safe=True)
        else:
            return None

    @staticmethod
    def render_total_check_count(record):
        total_check_count = ConformityCheckRun.objects.get_total_check_count(record)
        if total_check_count:
            link_to_list_of_runs = f'{reverse("quality:conformity_check_run_list")}?metadata={record.pk}'
            content = f'<span>{total_check_count}</span>'
            return Link(url=link_to_list_of_runs, content=content).render(safe=True)
        else:
            return None
