from datetime import datetime

from celery import chord
from django.contrib.gis.db import models
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from registry.models.metadata import DatasetMetadata
from registry.models.service import CatalougeService


class HarvestingJob(models.Model):
    """ helper model to visualize harvesting job workflow """
    service: CatalougeService = models.ForeignKey(
        to=CatalougeService,
        on_delete=models.CASCADE,
        verbose_name=_("service"),
        help_text=_("the csw for that this job is running"))
    total_records: int = models.IntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("total records"),
        help_text=_("total count of records which will be harvested by this job"))
    step_size: int = models.IntegerField(
        default=1,
        blank=True)
    started_at: datetime = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("date started"),
        help_text=_("timestamp of start"))
    done_at: datetime = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("date done"),
        help_text=_("timestamp of done"))
    new_records = models.ManyToManyField(
        to=DatasetMetadata,
        related_name="harvested_by",
        editable=False,)
    existing_records = models.ManyToManyField(
        to=DatasetMetadata,
        related_name="ignored_by",
        editable=False,)
    updated_records = models.ManyToManyField(
        to=DatasetMetadata,
        related_name="updated_by",
        editable=False,)

    # TODO: only one job per service allowed
    # class Meta:
    #     constraints = {
    #         models.CheckConstraint()
    #     }

    def save(self, *args, **kwargs) -> None:
        from registry.tasks.harvest import (  # to avoid circular import errors
            get_hits_task, get_records_task, set_done_at)
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            transaction.on_commit(
                lambda: get_hits_task.delay(harvesting_job_id=self.pk))
        elif self.total_records and not self.done_at:
            round_trips = (self.total_records // self.step_size)
            if self.total_records % self.step_size > 0:
                round_trips += 1
            tasks = []
            for number in range(1, round_trips+1):
                tasks.append(get_records_task.s(
                    harvesting_job_id=self.pk, start_position=number*self.step_size))
            transaction.on_commit(lambda: chord(tasks)(
                set_done_at.s(harvesting_job_id=self.pk)))
