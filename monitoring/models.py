"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""
import uuid
from datetime import datetime, timedelta

import pytz
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from MrMap.settings import TIME_ZONE
from monitoring.enums import HealthStateEnum
from monitoring.settings import WARNING_RESPONSE_TIME, CRITICAL_RESPONSE_TIME, DEFAULT_UNKNOWN_MESSAGE


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

    class Meta:
        ordering = ["-timestamp"]


class MonitoringCapability(Monitoring):
    needs_update = models.BooleanField(null=True, blank=True)
    diff = models.TextField(null=True, blank=True)


class HealthState(models.Model):
    monitoring_run = models.ForeignKey(MonitoringRun, on_delete=models.CASCADE, )
    metadata = models.ForeignKey('service.Metadata', on_delete=models.CASCADE, related_name='health_state', )
    health_state_code = models.CharField(default=HealthStateEnum.UNKNOWN.value,
                                         choices=HealthStateEnum.as_choices(drop_empty_choice=True),
                                         max_length=12)
    health_message = models.CharField(default=DEFAULT_UNKNOWN_MESSAGE,
                                      max_length=512, )     # this is the teaser for tooltips
    reliability_1w = models.FloatField(default=0,
                                       validators=[MaxValueValidator(100), MinValueValidator(1)])
    reliability_1m = models.FloatField(default=0,
                                       validators=[MaxValueValidator(100), MinValueValidator(1)])
    reliability_3m = models.FloatField(default=0,
                                       validators=[MaxValueValidator(100), MinValueValidator(1)])

    @staticmethod
    def _get_last_check_runs_on_msg(monitoring_result):
        return 'Last check runs on <span class="font-italic text-info">' + \
               f'{timezone.localtime(monitoring_result.monitoring_run.end).strftime("%Y-%m-%d %H:%M:%S")}</span>.<br>' + \
               'Click on this icon to see details.'

    def calculate_reliability(self):
        now = datetime.now()
        now_with_tz = pytz.utc.localize(now)

        health_states_3m = HealthState.objects.filter(metadata=self.metadata,
                                                      monitoring_run__end__gte=now-timedelta(days=90))\
                                              .order_by('-monitoring_run__end')
        # get only health states for 1m and 1w calculation to prevent from sql statements
        health_states_1m = list(filter(lambda _health_state: _health_state.monitoring_run.end > now_with_tz-timedelta(days=30), list(health_states_3m)))
        health_states_1w = list(filter(lambda _health_state: _health_state.monitoring_run.end > now_with_tz-timedelta(days=7), list(health_states_3m)))
        health_states_3m = list(health_states_3m)
        # append self, cause transaction is atomic in parent function,
        # so self would'nt be part of the calculation
        health_states_1w.append(self)
        health_states_1m.append(self)
        health_states_3m.append(self)

        reliability_1w = 0
        for health_state in health_states_1w:
            if health_state.health_state_code == HealthStateEnum.OK.value or health_state.health_state_code == HealthStateEnum.WARNING.value:
                reliability_1w += 1

        reliability_1m = 0
        for health_state in health_states_1m:
            if health_state.health_state_code == HealthStateEnum.OK.value or health_state.health_state_code == HealthStateEnum.WARNING.value:
                reliability_1m += 1

        reliability_3m = 0
        for health_state in health_states_3m:
            if health_state.health_state_code == HealthStateEnum.OK.value or health_state.health_state_code == HealthStateEnum.WARNING.value:
                reliability_3m += 1

        if health_states_1w:
            self.reliability_1w = reliability_1w * 100 / len(health_states_1w)
        if health_states_1m:
            self.reliability_1m = reliability_1m * 100 / len(health_states_1m)
        if health_states_3m:
            self.reliability_3m = reliability_3m * 100 / len(health_states_3m)
        self.save()

    def calculate_health_state(self, ):
        # Monitoring objects that are related to this run and given metadata
        monitoring_objects = Monitoring.objects.filter(monitoring_run=self.monitoring_run, metadata=self.metadata)

        if monitoring_objects:
            warning = False
            critical = False
            for monitoring_result in monitoring_objects:
                if not monitoring_result.available:
                    if monitoring_result.status_code == 401:
                        HealthStateReason(health_state=self,
                                          health_state_code=HealthStateEnum.UNAUTHORIZED.value,
                                          reason=_(
                                              f'The resource <span class="font-italic text-info">\'{monitoring_result.monitored_uri}\'</span> did response an exception.<br> '
                                              f'The http status code was <strong class="text-success">{monitoring_result.status_code}</strong>.'),
                                          monitoring_result=monitoring_result
                                          ).save()
                    else:
                        critical = True
                        if 200 <= monitoring_result.status_code <= 208:
                            HealthStateReason(health_state=self,
                                              health_state_code=HealthStateEnum.CRITICAL.value,
                                              reason=_(
                                                  f'The resource <span class="font-italic text-info">\'{monitoring_result.monitored_uri}\'</span> did response an exception.<br> '
                                                  f'The http status code was <strong class="text-success">{monitoring_result.status_code}</strong>.'),
                                              monitoring_result=monitoring_result,
                                              ).save()
                        else:
                            HealthStateReason(health_state=self,
                                              health_state_code=HealthStateEnum.CRITICAL.value,
                                              reason=_(
                                                  f'The resource <span class="font-italic text-info">\'{monitoring_result.monitored_uri}\'</span> did not response.<br> '
                                                  f'The http status code was <strong class="text-danger">{monitoring_result.status_code}</strong>.'),
                                              monitoring_result=monitoring_result,
                                              ).save()

                if monitoring_result.duration >= timedelta(milliseconds=CRITICAL_RESPONSE_TIME):
                    critical = True
                    HealthStateReason(health_state=self,
                                      health_state_code=HealthStateEnum.CRITICAL.value,
                                      reason=_(f'The response for <span class="font-italic text-info">\'{monitoring_result.monitored_uri}\'</span> took to long.<br> <strong class="text-danger">{monitoring_result.duration.microseconds / 1000} ms</strong> is greater than threshold <strong class="text-danger">{CRITICAL_RESPONSE_TIME} ms</strong>.'),
                                      monitoring_result=monitoring_result,
                                      ).save()
                elif monitoring_result.duration >= timedelta(milliseconds=WARNING_RESPONSE_TIME):
                    warning = True
                    HealthStateReason(health_state=self,
                                      health_state_code=HealthStateEnum.WARNING.value,
                                      reason=_(f'The response for <span class="font-italic text-info">\'{monitoring_result.monitored_uri}\'</span> took to long.<br> <strong class="text-warning">{monitoring_result.duration.microseconds / 1000} ms</strong> is greater than threshold <strong class="text-warning">{WARNING_RESPONSE_TIME} ms</strong>.'),
                                      monitoring_result=monitoring_result,
                                      ).save()

            if critical:
                self.health_state_code = HealthStateEnum.CRITICAL.value
                self.health_message = _('The state of this resource is <strong class="text-danger">critical</strong>.<br>' +
                                      self._get_last_check_runs_on_msg(monitoring_result))
            elif warning:
                self.health_state_code = HealthStateEnum.WARNING.value
                self.health_message = _('This resource has some <strong class="text-warning">warnings</strong>.<br>' +
                                      self._get_last_check_runs_on_msg(monitoring_result))
            else:
                # We can't found any errors. Health state is ok
                self.health_state_code = HealthStateEnum.OK.value
                self.health_message = _(f'Everthing is <strong class="text-success">OK</strong>.<br>' +
                                      self._get_last_check_runs_on_msg(monitoring_result))
            self.save()


class HealthStateReason(models.Model):
    health_state = models.ForeignKey(HealthState,
                                     on_delete=models.CASCADE,
                                     related_name='reasons', )
    reason = models.TextField(verbose_name=_('Reason'), )
    health_state_code = models.CharField(default=HealthStateEnum.UNKNOWN.value,
                                         choices=HealthStateEnum.as_choices(drop_empty_choice=True),
                                         max_length=12, )
    monitoring_result = models.ForeignKey(Monitoring, on_delete=models.CASCADE, related_name='health_state_reasons',)

