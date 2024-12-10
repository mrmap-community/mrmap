from logging import Logger

from celery import Task, shared_task
from celery.signals import task_prerun
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F
from django.utils.timezone import now
from django_celery_results.models import TaskResult
from notify.models import BackgroundProcess

logger: Logger = settings.ROOT_LOGGER


@task_prerun.connect
def get_background_process(task, *args, **kwargs):
    background_process_pk = kwargs["kwargs"].get("background_process_pk", None)
    if background_process_pk:
        try:
            task.background_process = BackgroundProcess.objects.get(
                pk=background_process_pk)
        except BackgroundProcess.ObjectDoesNotExist:
            pass


class BackgroundProcessBased(Task):
    thread_appended = False

    def update_background_process(
        self,
        phase: str = "",
        service=None,
        step_done=False,
        completed=False,
    ):
        # will be provided by get_background_process signal if the pk is provided by kwargs
        if hasattr(self, "background_process"):
            try:
                with transaction.atomic():
                    if not self.thread_appended:
                        # add the TaskResult if this function is called the first time
                        self.background_process.threads.add(
                            *TaskResult.objects.filter(task_id=self.request.id))
                        self.thread_appended = True
                    if phase:
                        bg_p = BackgroundProcess.objects.select_for_update().filter(
                            pk=self.background_process.pk)[0]
                        bg_p.phase = phase
                        bg_p.save()  # Do not directly update with sql!
                        # Otherwise the post_save signal is not triggered and
                        # no notifications will be send via websocket!
                    if service:
                        service_ct = ContentType.objects.get_for_model(service)
                        BackgroundProcess.objects.select_for_update().filter(
                            pk=self.background_process.pk).update(
                                related_resource_type=service_ct,
                                related_id=service.pk
                        )
                    if step_done:
                        bg_p = BackgroundProcess.objects.select_for_update().filter(
                            pk=self.background_process.pk)[0]
                        bg_p.done_steps += 1
                        bg_p.save()  # Do not directly update with sql!
                        # Otherwise the post_save signal is not triggered and
                        # no notifications will be send via websocket!
                    if completed:
                        bg_p = BackgroundProcess.objects.select_for_update().filter(
                            pk=self.background_process.pk).update(
                                done_steps=F("total_steps"),
                                done_at=now(),
                                phase="completed"
                        )
            except Exception as e:
                logger.exception(e, stack_info=True, exc_info=True)


@shared_task(
    bind=True,
    queue="db-routines",
    base=BackgroundProcessBased
)
def finish_background_process(
    self,
    **kwargs
):
    self.update_background_process(
        completed=True
    )
