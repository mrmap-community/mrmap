"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""
from itertools import chain

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import PeriodicTask, CrontabSchedule

from MrMap.settings import TIME_ZONE
from main.models import CommonInfo, GenericModelMixin
from main.polymorphic_fk import PolymorphicForeignKey
from monitoring.enums import HealthStateEnum
from monitoring.settings import WARNING_RESPONSE_TIME, CRITICAL_RESPONSE_TIME, DEFAULT_UNKNOWN_MESSAGE


# TODO is this class effectively used for any functionality? Can it be removed?
class MonitoringSetting(models.Model):
    # TODO other resource types
    metadatas = models.ManyToManyField('registry.Service', related_name='monitoring_setting')
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


class MonitoringRun(CommonInfo, GenericModelMixin):
    start = models.DateTimeField(null=True, blank=True)
    end = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    services = models.ManyToManyField('registry.Service',
                                      related_name='monitoring_runs', blank=True,
                                      verbose_name=_('Checked services'))
    layers = models.ManyToManyField('registry.Layer',
                                    related_name='monitoring_runs', blank=True,
                                    verbose_name=_('Checked layers'))
    feature_types = models.ManyToManyField('registry.FeatureType',
                                           related_name='monitoring_runs', blank=True,
                                           verbose_name=_('Checked feature types'))
    dataset_metadatas = models.ManyToManyField('registry.DatasetMetadata',
                                               related_name='monitoring_runs', blank=True,
                                               verbose_name=_('Checked dataset metadatas'))

    class Meta:
        ordering = ["-end"]
        verbose_name = _('Monitoring run')
        verbose_name_plural = _('Monitoring runs')

    def __str__(self):
        return str(self.id)

    @property
    def resources_all(self):
        return list(
            chain(self.services.all(), self.layers.all(), self.feature_types.all(), self.dataset_metadatas.all()))

    @property
    def result_view_uri(self):
        return f"{MonitoringResult.get_table_url()}?monitoring_run={self.id}"

    @property
    def health_state_view_uri(self):
        return f"{HealthState.get_table_url()}?monitoring_run={self.id}"

    def save(self, *args, **kwargs):
        adding = False
        if self._state.adding:
            adding = True
        super().save(*args, **kwargs)
        if adding:
            from monitoring.tasks import run_manual_service_monitoring
            transaction.on_commit(lambda: run_manual_service_monitoring.apply_async(
                args=(self.owned_by_org.pk if self.owned_by_org else None,
                      self.pk,),
                kwargs={'created_by_user_pk': self.created_by_user.pk},
                countdown=settings.CELERY_DEFAULT_COUNTDOWN))


class MonitoringResult(CommonInfo, GenericModelMixin):
    # polymorphic fk (either service, layer, feature type or dataset metadata)
    service = models.ForeignKey('registry.Service', on_delete=models.CASCADE, null=True, blank=True,
                                verbose_name=_('Service'))
    layer = models.ForeignKey('registry.Layer', on_delete=models.CASCADE, null=True, blank=True,
                              verbose_name=_('Layer'))
    feature_type = models.ForeignKey('registry.FeatureType', on_delete=models.CASCADE, null=True, blank=True,
                                     verbose_name=_('Feature Type'))
    dataset_metadata = models.ForeignKey('registry.DatasetMetadata', on_delete=models.CASCADE, null=True, blank=True,
                                         verbose_name=_('Dataset Metadata'))
    _resource = PolymorphicForeignKey('service', 'layer', 'feature_type', 'dataset_metadata')

    timestamp = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    error_msg = models.TextField(null=True, blank=True)
    available = models.BooleanField(null=True)
    monitored_uri = models.CharField(max_length=2000)
    monitoring_run = models.ForeignKey(MonitoringRun, on_delete=models.CASCADE, related_name='monitoring_results')

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = _('Monitoring result')
        verbose_name_plural = _('Monitoring results')

    # TODO consider integrating this into PolymorphicForeignKey
    @property
    def resource(self):
        return self._resource.get_target(self)

    # TODO consider integrating this into PolymorphicForeignKey
    @resource.setter
    def resource(self, value):
        self._resource.set_target(self, value)


class MonitoringResultDocument(MonitoringResult):
    """Model used to signal if a given document differs from the remote document and needs an update"""
    needs_update = models.BooleanField(null=True, blank=True)
    diff = models.TextField(null=True, blank=True)


class HealthState(CommonInfo, GenericModelMixin):
    monitoring_run = models.ForeignKey(MonitoringRun, on_delete=models.CASCADE, related_name='health_states',
                                       verbose_name=_('Monitoring Runs'))

    # polymorphic fk (either service, layer, feature type or dataset metadata)
    service = models.ForeignKey('registry.Service', on_delete=models.CASCADE, related_name='health_states',
                                related_query_name='health_states', null=True, blank=True, verbose_name=_('Service'))
    layer = models.ForeignKey('registry.Layer', on_delete=models.CASCADE, related_name='health_states',
                              related_query_name='health_states', null=True, blank=True, verbose_name=_('Layer'))
    feature_type = models.ForeignKey('registry.FeatureType', on_delete=models.CASCADE, related_name='health_states',
                                     related_query_name='health_states', null=True, blank=True,
                                     verbose_name=_('Feature Type'))
    dataset_metadata = models.ForeignKey('registry.DatasetMetadata', on_delete=models.CASCADE,
                                         related_name='health_states',
                                         related_query_name='health_states', null=True, blank=True,
                                         verbose_name=_('Dataset Metadata'))
    _resource = PolymorphicForeignKey('service', 'layer', 'feature_type', 'dataset_metadata')

    health_state_code = models.CharField(default=HealthStateEnum.UNKNOWN.value,
                                         choices=HealthStateEnum.as_choices(drop_empty_choice=True),
                                         max_length=12, verbose_name=_('Health state code'))
    health_message = models.CharField(default=DEFAULT_UNKNOWN_MESSAGE,
                                      max_length=512, )  # this is the teaser for tooltips
    reliability_1w = models.FloatField(default=0,
                                       validators=[MaxValueValidator(100), MinValueValidator(1)])
    reliability_1m = models.FloatField(default=0,
                                       validators=[MaxValueValidator(100), MinValueValidator(1)])
    reliability_3m = models.FloatField(default=0,
                                       validators=[MaxValueValidator(100), MinValueValidator(1)])
    average_response_time = models.DurationField(null=True, blank=True)
    average_response_time_1w = models.DurationField(null=True, blank=True)
    average_response_time_1m = models.DurationField(null=True, blank=True)
    average_response_time_3m = models.DurationField(null=True, blank=True)

    class Meta:
        ordering = ['-monitoring_run__start']
        verbose_name = _('Health state')
        verbose_name_plural = _('Health states')

    # TODO consider integrating this into the PolymorphicForeignKey
    @property
    def resource(self):
        return self._resource.get_target(self)

    # TODO consider integrating this into the PolymorphicForeignKey
    @resource.setter
    def resource(self, value):
        self._resource.set_target(self, value)

    @property
    def result_view_uri(self):
        return f"{MonitoringResult.get_table_url()}?monitoring_run={self.monitoring_run_id}&resource={self.resource.id}"

    @staticmethod
    def _get_last_check_runs_on_msg(monitoring_result):
        return 'Last check runs on <span class="font-italic text-info">' + \
               f'{timezone.localtime(monitoring_result.monitoring_run.end).strftime("%Y-%m-%d %H:%M:%S")}</span>.<br>' + \
               'Click on this icon to see details.'

    def run_health_state(self):
        resource_field = self._resource.get_target_field(self)
        resource_value = self._resource.get_target(self)

        # Monitoring objects that are related to this run and given metadata
        monitoring_objects = MonitoringResult.objects.filter(monitoring_run=self.monitoring_run,
                                                             **{resource_field: resource_value})
        # Get health states of the last 3 months, for statistic calculating
        now = timezone.now()
        health_states_3m = HealthState.objects.filter(
            monitoring_run__end__gte=now - timezone.timedelta(days=(3 * 365 / 12)),
            **{resource_field: resource_value}) \
            .order_by('-monitoring_run__end')

        # get only health states for 1m and 1w calculation to prevent from sql statements
        health_states_1m = list(
            filter(lambda _health_state: _health_state.monitoring_run.end > now - timezone.timedelta(days=(365 / 12)),
                   list(health_states_3m)))
        health_states_1w = list(
            filter(lambda _health_state: _health_state.monitoring_run.end > now - timezone.timedelta(days=7),
                   list(health_states_3m)))
        health_states_3m = list(health_states_3m)
        # append self, cause transaction is atomic in parent function,
        # so self would'nt be part of any calculation
        health_states_1w.append(self)
        health_states_1m.append(self)
        health_states_3m.append(self)

        self._calculate_average_response_times(monitoring_objects=monitoring_objects,
                                               health_states_1w=health_states_1w,
                                               health_states_1m=health_states_1m,
                                               health_states_3m=health_states_3m)
        self._calculate_health_state(monitoring_objects=monitoring_objects)
        self._calculate_reliability(health_states_1w=health_states_1w,
                                    health_states_1m=health_states_1m,
                                    health_states_3m=health_states_3m)

    def _calculate_average_response_times(self, monitoring_objects, health_states_1w, health_states_1m,
                                          health_states_3m):
        if monitoring_objects:
            average_response_time = None
            for monitoring_result in monitoring_objects:
                if not average_response_time:
                    average_response_time = monitoring_result.duration
                else:
                    average_response_time += monitoring_result.duration
            self.average_response_time = average_response_time / len(monitoring_objects)
            self.save()

            average_response_time_1w = None
            for health_state in health_states_1w:
                if average_response_time_1w:
                    average_response_time_1w += health_state.average_response_time
                else:
                    average_response_time_1w = health_state.average_response_time
            self.average_response_time_1w = average_response_time_1w / len(health_states_1w)

            average_response_time_1m = None
            for health_state in health_states_1m:
                if average_response_time_1m:
                    average_response_time_1m += health_state.average_response_time
                else:
                    average_response_time_1m = health_state.average_response_time
            self.average_response_time_1m = average_response_time_1m / len(health_states_1m)

            average_response_time_3m = None
            for health_state in health_states_3m:
                if average_response_time_3m:
                    average_response_time_3m += health_state.average_response_time
                else:
                    average_response_time_3m = health_state.average_response_time
            self.average_response_time_3m = average_response_time_3m / len(health_states_3m)

            self.save()

    def _calculate_reliability(self, health_states_1w, health_states_1m, health_states_3m):
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

    def _calculate_health_state(self, monitoring_objects):
        if monitoring_objects:
            warning = False
            critical = False

            for monitoring_result in monitoring_objects:
                # evaluate availability
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

            # evaluate response time
            if self.average_response_time_1w >= timezone.timedelta(milliseconds=CRITICAL_RESPONSE_TIME):
                critical = True
                HealthStateReason(health_state=self,
                                  health_state_code=HealthStateEnum.CRITICAL.value,
                                  reason=_(
                                      f'The average response time for 1 week statistic is too high.<br> <strong class="text-danger">{self.average_response_time_1w.total_seconds() * 1000} ms</strong> is greater than threshold <strong class="text-danger">{CRITICAL_RESPONSE_TIME} ms</strong>.'),
                                  monitoring_result=monitoring_result,
                                  ).save()
            elif self.average_response_time_1w >= timezone.timedelta(milliseconds=WARNING_RESPONSE_TIME):
                warning = True
                HealthStateReason(health_state=self,
                                  health_state_code=HealthStateEnum.WARNING.value,
                                  reason=_(
                                      f'The average response time for 1 week statistic is too high.<br> <strong class="text-danger">{self.average_response_time_1w.total_seconds() * 1000} ms</strong> is greater than threshold <strong class="text-danger">{WARNING_RESPONSE_TIME} ms</strong>.'),
                                  monitoring_result=monitoring_result,
                                  ).save()

            if critical:
                self.health_state_code = HealthStateEnum.CRITICAL.value
                self.health_message = _(
                    'The state of this resource is <strong class="text-danger">critical</strong>.<br>' +
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
    monitoring_result = models.ForeignKey(MonitoringResult, on_delete=models.CASCADE,
                                          related_name='health_state_reasons', )
