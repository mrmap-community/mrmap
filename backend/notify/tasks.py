from logging import Logger

from celery import Task, shared_task
from celery.signals import task_prerun
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save
from django.utils.timezone import now
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.exceptions.harvesting import InternalServerError
from requests.exceptions import ConnectionError, Timeout

logger: Logger = settings.ROOT_LOGGER


@task_prerun.connect
def get_background_process(task, *args, **kwargs):
    """To automaticly get the BackgroundProcess object on task runtime."""
    task.background_process_pk = kwargs["kwargs"].get(
        "background_process_pk", None)
    if isinstance(task, BackgroundProcessBased) and task.background_process_pk is not None:
        task.update_background_process()


class BackgroundProcessBased(Task):
    thread_appended = False
    autoretry_for = (Timeout, ConnectionError, InternalServerError)
    retry_backoff = 30
    retry_backoff_max = 5*60
    retry_jitter = False
    max_retries = 10

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self.update_background_process(
            phase=f"An error occurred: {exc}"[:512],
            failed=True
        )

    def update_state(self, task_id=None, state=None, meta=None, **kwargs):
        pass
        # return super().update_state(task_id, state, meta, **kwargs)

    def update_background_process(
        self,
        phase: str = "",
        service=None,
        total_steps=None,
        step_done=False,
        completed=False,
        failed=False,
    ):
        # will be provided by get_background_process signal if the pk is provided by kwargs
        if getattr(self, "background_process_pk", None) is not None:
            try:
                query = BackgroundProcess.objects.filter(
                    pk=self.background_process_pk)
                kwargs = {"status": ProcessStatusEnum.RUNNING}

                if phase:
                    kwargs.update({
                        "phase": phase
                    })
                if service:
                    kwargs.update({
                        "related_resource_type": ContentType.objects.get_for_model(service),
                        "related_id": service.pk
                    })
                if total_steps is not None:
                    kwargs.update({
                        "total_steps": total_steps
                    })
                if step_done:
                    kwargs.update({
                        "done_steps": F("done_steps") + 1
                    })
                if failed:
                    kwargs.update({"status": ProcessStatusEnum.FAILED, "done_at": now()})
                elif completed:
                    kwargs.update({
                        "total_steps": Coalesce(F("total_steps"), 1),
                        "done_steps": Coalesce(F("total_steps"), 1),
                        "done_at": now(),
                        "phase": "completed",
                        "status": ProcessStatusEnum.COMPLETED
                    })

                if kwargs:
                    # A terminal outcome cannot be overwritten by sibling tasks.
                    active_query = query.filter(
                        done_at__isnull=True,
                        status__in=[ProcessStatusEnum.PENDING, ProcessStatusEnum.RUNNING])
                    if kwargs == {"status": ProcessStatusEnum.RUNNING}:
                        # get_background_process fires on every task start; for a
                        # process which is already running this writes nothing and
                        # must not broadcast anything either.
                        active_query = active_query.exclude(
                            status=ProcessStatusEnum.RUNNING)
                    updated = active_query.update(**kwargs)

                    if updated:
                        try:
                            # process_info provides the progress annotation and
                            # the related resource type in one go, so the
                            # post_save receiver doesn't have to reload.
                            instance = BackgroundProcess.objects.process_info().get(
                                pk=self.background_process_pk)
                            post_save.send(
                                BackgroundProcess,
                                instance=instance,
                                created=False
                            )
                        except BackgroundProcess.DoesNotExist:
                            logger.warning(
                                f"Can't get BackgroundProcess by id {self.background_process_pk}")

            except Exception as e:
                logger.exception(e, stack_info=True, exc_info=True)
        else:
            logger.warning(
                f"No background process provided for BackgroundProcessBased task. {self.name}")


@shared_task(
    bind=True,
    queue="db-routines",
    base=BackgroundProcessBased
)
def finish_background_process(
    self,
    *args,
    **kwargs
):
    self.update_background_process(
        completed=True
    )
