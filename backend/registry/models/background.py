
from black import out
from celery.states import FAILURE, PENDING, STARTED, SUCCESS
from django.db import models
from django.db.models import BooleanField, Case, Count, Manager, Q, Value, When
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from MrMap.enums import EnumChoice


class ProcessNameEnum(EnumChoice):
    HARVESTING = 'harvesting'
    MONITORING = 'monitoring'


class BackgroundProcessQuerySet(models.QuerySet):
    def pending_threads(self):
        return self.filter(threads__status=PENDING)

    def running_threads(self):
        return self.filter(threads__status=STARTED)

    def successed_threads(self):
        return self.filter(threads__status=SUCCESS)

    def failed_threads(self):
        return self.filter(threads__status=FAILURE)

    def first_runned_thread(self):
        return (self.successed_threads() | self.failed_threads() | self.failed_threads()).order_by('-threads__date_created').first()

    def last_runned_thread(self):
        return (self.successed_threads() | self.failed_threads() | self.failed_threads()).order_by('-threads__date_done').first()

    def process_info(self):
        return self.annotate(
            pending_threads=Count(self.pending_threads),
            running_threads=Count(self.running_threads),
            successed_threads=Count(self.successed_threads),
            failed_threads=Count(self.failed_threads),
            # date_created=self.first_runned_thread().values('threads__date_created')
        ).annotate(
            is_done=Case(
                cases=When(
                    condition=Q(running_threads__lt=0, pending_threads__lt=0),
                    then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            has_failures=Case(
                cases=When(
                    condition=Q(failed_threads__gt=0),
                    then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        )

    def harvesting_processes(self):
        return self.filter(name=ProcessNameEnum.HARVESTING.value)

    def monitoring_processes(self):
        return self.filter(name=ProcessNameEnum.MONITORING.value)


class BackgroundProcess(models.Model):
    threads = models.ManyToManyField(
        to=TaskResult,
        related_name='processes',
        related_query_name='process')
    phase = models.CharField(
        max_length=256,
        verbose_name=_('phase'),
        help_text=_('Current phase of the process'))
    name = models.CharField(
        max_length=32,
        choices=ProcessNameEnum.as_choices(drop_empty_choice=True),
        verbose_name=_('name'),
        help_text=_('Human readable short name of this process'))
    description = models.CharField(
        max_length=128,
        verbose_name=_('description'),
        help_text=_('Human readable description of what this process does')
    )

    class Meta:
        abstract = True
        verbose_name = _('Background Process')
        verbose_name_plural = _('Background Processes')

    objects = Manager.from_queryset(BackgroundProcessQuerySet)()
