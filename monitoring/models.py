"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""
import re
import uuid
from datetime import timedelta

from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from django.utils.translation import gettext_lazy as _

from MrMap.settings import TIME_ZONE
from monitoring.enums import HealthStateEnum
from monitoring.settings import WARNING_RESPONSE_TIME, CRITICAL_RESPONSE_TIME, SUCCESS_HTTP_CODE_REGEX, \
    monitoring_logger, DEFAULT_UNKNOWN_MESSAGE


def _get_last_check_runs_on_msg(monitoring_result):
    return f'Last check runs on <span class="font-italic text-info">{monitoring_result.monitoring_run.start.strftime("%Y-%m-%d %H:%M:%S")}</span>.<br>'


class HealthState(models.Model):
    health_state_code = models.CharField(default=HealthStateEnum.UNKNOWN.value, choices=HealthStateEnum.as_choices(drop_empty_choice=True), max_length=10)
    health_message = models.TextField(default=DEFAULT_UNKNOWN_MESSAGE, null=True, blank=True)

    def calculate_health_state(self):
        monitoring_objects = Monitoring.objects.filter(health_state=self)  # Monitoring objects that are related to this health state

        if monitoring_objects:
            warning = False
            warning_reasons = []
            critical = False
            critical_reasons = []
            for monitoring_result in monitoring_objects:
                if not re.match(SUCCESS_HTTP_CODE_REGEX, str(monitoring_result.status_code)):
                    critical = True
                    critical_reasons.append(
                        f'The resource <span class="font-italic">\'{monitoring_result.monitored_uri}\'</span> did not response.<br> The http status code was <strong class="text-danger">{monitoring_result.status_code}</strong>.<br>')
                if monitoring_result.duration >= timedelta(milliseconds=CRITICAL_RESPONSE_TIME):
                    critical = True
                    critical_reasons.append(
                        f'The response for <span class="font-italic">\'{monitoring_result.monitored_uri}\'</span> took to long. <strong class="text-danger">{monitoring_result.duration.microseconds / 1000} ms</strong> is greater than threshold <strong class="text-danger">{CRITICAL_RESPONSE_TIME} ms</strong>.<br>')
                elif monitoring_result.duration >= timedelta(milliseconds=WARNING_RESPONSE_TIME):
                    warning = True
                    warning_reasons.append(
                        f'The response for <span class="font-italic">\'{monitoring_result.monitored_uri}\'</span> took to long.  <strong class="text-warning">{monitoring_result.duration.microseconds / 1000} ms</strong> is greater than threshold <strong class="text-warning">{WARNING_RESPONSE_TIME} ms</strong>.<br>')
            if critical:
                self.health_state_code = HealthStateEnum.CRITICAL.value
                self.health_message = 'The state of this resource is <strong class="text-danger">critical</strong>.<br>' + \
                                      ' '.join(critical_reasons) + \
                                      ' '.join(warning_reasons) + \
                                      _get_last_check_runs_on_msg(monitoring_result)
            elif warning:
                self.health_state_code = HealthStateEnum.WARNING.value
                self.health_message = 'This resource has some <strong class="text-warning">warnings</strong>.<br>' + \
                                      ' '.join(warning_reasons) + \
                                      _get_last_check_runs_on_msg(monitoring_result)
            else:
                # We can't found any errors. Health state is ok
                self.health_state_code = HealthStateEnum.OK.value
                self.health_message = _(f'Everthing is <strong class="text-success">OK</strong>.<br>') + \
                                      _get_last_check_runs_on_msg(monitoring_result)

            self.save()


class MonitoringSetting(models.Model):
    metadatas = models.ManyToManyField('service.Metadata', related_name='monitoring_setting')
    check_time = models.TimeField()
    timeout = models.IntegerField()
    periodic_task = models.OneToOneField(PeriodicTask, on_delete=models.CASCADE, null=True, blank=True)

    def update_periodic_tasks(self):
        """ Updates related PeriodicTask record based on the current MonitoringSetting

        Returns:

        """
        time = self.check_time
        schedule = CrontabSchedule.objects.get_or_create(
            minute=time.minute,
            hour=time.hour,
            timezone=TIME_ZONE,
        )[0]

        if self.periodic_task is not None:
            # Update interval to latest setting
            self.periodic_task.crontab = schedule
            self.periodic_task.save()
        else:
            # Create new PeriodicTask
            try:
                task = PeriodicTask.objects.get_or_create(
                    task='run_service_monitoring',
                    name=f'monitoring_setting_{self.id}',
                    args=f'[{self.id}]'
                )[0]
                task.crontab = schedule
                task.save()
                self.periodic_task = task
            except ValidationError as e:
                pass

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """ Overwrites default save method.

        Updates related PeriodicTask to match the current state of MonitoringSetting.

        Args:
            force_insert:
            force_update:
            using:
            update_fields:
        Returns:

        """
        self.update_periodic_tasks()
        super().save(force_insert, force_update, using, update_fields)


class MonitoringRun(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    start = models.DateTimeField(auto_now_add=True)
    end = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)

    class Meta:
        ordering = ["-end"]


class Monitoring(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    metadata = models.ForeignKey('service.Metadata', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    error_msg = models.TextField(null=True, blank=True)
    available = models.BooleanField(null=True)
    monitored_uri = models.CharField(max_length=2000)
    monitoring_run = models.ForeignKey(MonitoringRun, on_delete=models.CASCADE, related_name='monitoring_results')
    health_state = models.ForeignKey(HealthState, on_delete=models.CASCADE, related_name='monitoring_results')

    class Meta:
        ordering = ["-timestamp"]


class MonitoringCapability(Monitoring):
    needs_update = models.BooleanField(null=True, blank=True)
    diff = models.TextField(null=True, blank=True)
