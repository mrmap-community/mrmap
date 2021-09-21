import logging

import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from MrMap.icons import get_icon, IconEnum
from extras.tables.tables import SecuredTable
from extras.tables.template_code import DEFAULT_ACTION_BUTTONS, VALUE_ABSOLUTE_LINK
from quality.models import ConformityCheckRun

# Get an instance of a logger
logger = logging.getLogger(__name__)


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

    @staticmethod
    def render_report(record):
        content = f'<span><a href={record.get_report_url()}>{_("Validation report")} </a></span>'
        return format_html(content)


class ConformityCheckRunExtraFieldsTable(tables.Table):
    latest_check = tables.Column(verbose_name=_('Latest check'),
                                 attrs={"th": {"class": "col-sm-1"}},
                                 empty_values=[_("No Conformity Check available")])

    linked_conformity_check_count = tables.Column(verbose_name=_('Latest check'),
                                                  attrs={"th": {"class": "col-sm-1"}},
                                                  empty_values=[_("No Conformity Check available")])

    class Meta:
        fields = ["latest_check", "linked_conformity_check_count"]
        prefix = "conformity_check_run-extra-fields-table"

    @staticmethod
    def render_latest_check(record):
        if record.linked_conformity_check_count > 0:
            latest_check_creation_datetime_str = record.latest_check_date.strftime("%m/%d/%Y %I:%M%p")
            latest_check_passed = record.latest_check_status
            if latest_check_passed is True:
                icon = get_icon(IconEnum.OK, 'text-success')
            elif latest_check_passed is False:
                icon = get_icon(IconEnum.NOK, 'text-danger')
            else:
                icon = get_icon(IconEnum.PENDING, 'text-warning')

            link_to_report = reverse('quality:conformity_check_run_report', kwargs={'pk': record.latest_check_pk})
            content = f'<span><a href={link_to_report}>{latest_check_creation_datetime_str} </a>{icon}</span>'
            return format_html(content)
        else:
            return _("No Conformity Check available")

    @staticmethod
    def render_linked_conformity_check_count(record, value):
        if value > 0:
            link_to_list_of_runs = f'{reverse("quality:conformity_check_run_list")}?metadata={record.pk}'
            content = f'<span><a href={link_to_list_of_runs}>{value} </a></span>'
            return format_html(content)
        else:
            return _("No Conformity Check available")

