import django_tables2 as tables
from django.template import Template, Context
from main.enums.bootstrap import ProgressColorEnum
from django.utils.html import format_html
from MrMap.icons import IconEnum, get_icon
from django.utils.translation import gettext_lazy as _
from MrMap.templatecodes import PROGRESS_BAR, TOOLTIP
from job.models import Job, Task
from job.enums import TaskStatusEnum
from main.tables.template_code import RECORD_ABSOLUTE_LINK_VALUE_CONTENT


class JobTable(tables.Table):
    status = tables.Column(verbose_name=_('Status'),
                           attrs={"th": {"class": "col-sm-1"}})
    details = tables.TemplateColumn(accessor="pk",
                                    verbose_name=_("details"),
                                    template_code=RECORD_ABSOLUTE_LINK_VALUE_CONTENT)
    created_by_user = tables.Column(attrs={"th": {"class": "col-sm-1"}})
    name = tables.Column(attrs={"th": {"class": "col-sm-1"}})
    created_at = tables.Column(verbose_name=_('Date Created'),
                               attrs={"th": {"class": "col-sm-1"}},
                               empty_values=[])
    done_at = tables.Column(verbose_name=_('Date Done'),
                            attrs={"th": {"class": "col-sm-1"}},
                            empty_values=[])
    execution_time = tables.Column(verbose_name=_("Execution time"),
                                   attrs={"th": {"class": "col-sm-2"}})
    progress = tables.Column(verbose_name=_('Progress'),
                             attrs={"th": {"class": "col-sm-2"}},
                             empty_values=[])

    class Meta:
        model = Job
        fields = ('status',
                  "name",
                  'created_by_user',
                  'created_at',
                  'done_at',
                  'execution_time',
                  'progress')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'pending-task-table'
        orderable = False

    def render_status(self, value):
        icon = ''
        tooltip = ''
        if value == TaskStatusEnum.PENDING.value:
            icon = get_icon(IconEnum.PENDING, 'text-warning')
            tooltip = _('Task is pending')
        elif value == TaskStatusEnum.STARTED.value:
            icon = get_icon(IconEnum.PLAY, 'text-success')
            tooltip = _('Task is running')
        elif value == TaskStatusEnum.SUCCESS.value:
            icon = get_icon(IconEnum.OK, 'text-success')
            tooltip = _('Task successfully done')
        elif value == TaskStatusEnum.FAILURE.value:
            icon = get_icon(IconEnum.CRITICAL, 'text-danger')
            tooltip = _('Task unexpected stopped')
        # use Template with templatecode to speed up rendering
        context = Context()
        context.update({'content': icon,
                        'tooltip': tooltip})
        return Template(TOOLTIP).render(context)

    @staticmethod
    def render_progress(record, value):
        color = None
        animated = True
        if record.status == TaskStatusEnum.SUCCESS.value:
            color = ProgressColorEnum.SUCCESS
            animated = False
        if record.status == TaskStatusEnum.FAILURE.value:
            color = ProgressColorEnum.DANGER
            animated = False
        # use Template with templatecode to speed up rendering
        context = Context()
        context.update({'value': round(value, 2),
                        'color': color.value if color else None,
                        'animated': animated,
                        'striped': animated})
        return Template(PROGRESS_BAR).render(context)


class TaskTable(tables.Table):
    status = tables.Column(verbose_name=_('Status'),
                           attrs={"th": {"class": "col-sm-1"}})
    created_by_user = tables.Column(attrs={"th": {"class": "col-sm-1"}})
    phase = tables.Column(attrs={"th": {"class": "col-sm-1"}})
    started_at = tables.Column(verbose_name=_('Started at'),
                               attrs={"th": {"class": "col-sm-1"}},
                               empty_values=[])
    done_at = tables.Column(verbose_name=_('Done at'),
                            attrs={"th": {"class": "col-sm-1"}},
                            empty_values=[])
    execution_time = tables.Column(verbose_name=_("Execution time"),
                                   attrs={"th": {"class": "col-sm-2"}})
    progress = tables.Column(verbose_name=_('Progress'),
                             attrs={"th": {"class": "col-sm-2"}},
                             empty_values=[])

    class Meta:
        model = Task
        fields = ('status',
                  "name",
                  "phase",
                  'created_by_user',
                  'started_at',
                  'done_at',
                  'execution_time',
                  'progress')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'pending-task-table'
        orderable = False

    def render_status(self, value):
        icon = ''
        tooltip = ''
        if value == TaskStatusEnum.PENDING.value:
            icon = get_icon(IconEnum.PENDING, 'text-warning')
            tooltip = _('Task is pending')
        elif value == TaskStatusEnum.STARTED.value:
            icon = get_icon(IconEnum.PLAY, 'text-success')
            tooltip = _('Task is running')
        elif value == TaskStatusEnum.SUCCESS.value:
            icon = get_icon(IconEnum.OK, 'text-success')
            tooltip = _('Task successfully done')
        elif value == TaskStatusEnum.FAILURE.value:
            icon = get_icon(IconEnum.CRITICAL, 'text-danger')
            tooltip = _('Task unexpected stopped')
        # use Template with templatecode to speed up rendering
        context = Context()
        context.update({'content': icon,
                        'tooltip': tooltip})
        return Template(TOOLTIP).render(context)

    def render_phase(self, value):
        return format_html(value)

    @staticmethod
    def render_progress(record, value):
        color = None
        animated = True
        if record.status == TaskStatusEnum.SUCCESS.value:
            color = ProgressColorEnum.SUCCESS
            animated = False
        if record.status == TaskStatusEnum.FAILURE.value:
            color = ProgressColorEnum.DANGER
            animated = False
        # use Template with templatecode to speed up rendering
        context = Context()
        context.update({'value': round(value, 2),
                        'color': color.value if color else None,
                        'animated': animated,
                        'striped': animated})
        return Template(PROGRESS_BAR).render(context)
