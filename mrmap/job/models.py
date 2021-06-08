from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.db.models import Avg
from job.enums import TaskStatusEnum
from job.managers import TaskManager
from main.models import CommonInfo
from django.urls import reverse


class Job(CommonInfo):
    """ Django model to represent a set of tasks. It gives a summery view of all tasks which are part of this job. """
    name = models.CharField(max_length=256,
                            verbose_name=_("name"),
                            help_text=_("Describe what this job does."))

    @cached_property
    def cached_tasks(self):
        try:
            return self.tasks.all()
        except Task.DoesNotExist:
            return Task.objects.none()

    @cached_property
    def status(self):
        if any(task.status == TaskStatusEnum.FAILURE.value for task in self.cached_tasks):
            return TaskStatusEnum.FAILURE.value
        elif any(task.status == TaskStatusEnum.STARTED.value for task in self.cached_tasks):
            return TaskStatusEnum.STARTED.value
        elif any(task.status == TaskStatusEnum.SUCCESS.value for task in self.cached_tasks) and not \
             any(task.status == TaskStatusEnum.PENDING.value for task in self.cached_tasks):
            return TaskStatusEnum.SUCCESS.value
        else:
            return TaskStatusEnum.PENDING.value

    @cached_property
    def progress(self):
        progress = self.cached_tasks.aggregate(progress=Avg('progress')).get("progress")
        return progress if progress else 0

    @cached_property
    def started_at(self):
        return self.cached_tasks.order_by("started_at").values_list("started_at", flat=True).first()

    @cached_property
    def done_at(self):
        if any(task.done_at is None for task in self.cached_tasks):
            return None
        return self.cached_tasks.order_by("-done_at").values_list("done_at", flat=True).first()

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"{reverse('job:task_list')}?job__in={self.pk}"


class Task(CommonInfo):
    """ Django model store celery task processing. A task is always a part of a job which contains one or more tasks."""
    status = models.CharField(
        max_length=50,
        default=TaskStatusEnum.PENDING.value,
        choices=TaskStatusEnum.as_choices(),
        verbose_name=_('task state'),
        help_text=_('Current state of the task being run'))
    phase = models.CharField(max_length=256,
                             default="")
    progress = models.FloatField(default=0.0)
    started_at = models.DateTimeField(null=True,
                                      blank=True)
    done_at = models.DateTimeField(null=True,
                                   blank=True)
    traceback = models.TextField(null=True,
                                 blank=True)
    job = models.ForeignKey(to=Job,
                            on_delete=models.CASCADE,
                            related_name="tasks",
                            related_query_name="task",
                            verbose_name=_("parent task"),
                            help_text=_("the parent task of this sub task"))

    objects = TaskManager()

    def __str__(self):
        return f"{self.pk} | {self.status} | {self.progress}"
