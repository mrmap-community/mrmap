from logging import Logger

from celery import Task, shared_task
from celery.signals import task_prerun
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save
from django.utils.timezone import now
from notify.models import BackgroundProcess
from registry.exceptions.harvesting import InternalServerError
from requests.exceptions import ConnectionError, Timeout

logger: Logger = settings.ROOT_LOGGER


@task_prerun.connect
def get_background_process(task, *args, **kwargs):
    """To automaticly get the BackgroundProcess object on task runtime."""
    task.background_process_pk = kwargs["kwargs"].get(
        "background_process_pk", None)


class BackgroundProcessBased(Task):
    thread_appended = False
    autoretry_for = (Timeout, ConnectionError, InternalServerError)
    retry_backoff = 30
    retry_backoff_max = 5*60
    retry_jitter = False
    max_retries = 10

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self.update_background_process(
            phase=f"An error occours: {einfo}",
            completed=True
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
    ):
        # will be provided by get_background_process signal if the pk is provided by kwargs
        if hasattr(self, "background_process_pk"):
            try:
                query = BackgroundProcess.objects.filter(
                    pk=self.background_process_pk)
                kwargs = {}
                send_post_save = False

                if phase:
                    kwargs.update({
                        "phase": phase
                    })
                    send_post_save = True
                if service:
                    kwargs.update({
                        "related_resource_type": ContentType.objects.get_for_model(service),
                        "related_id": service.pk
                    })
                if total_steps:
                    kwargs.update({
                        "total_steps": total_steps
                    })
                if step_done:
                    kwargs.update({
                        "done_steps": F("done_steps") + 1
                    })
                    send_post_save = True
                if completed:
                    kwargs.update({
                        "total_steps": Coalesce(F("total_steps"), 1),
                        "done_steps": Coalesce(F("total_steps"), 1),
                        "done_at": now(),
                        "phase": "completed"
                    })
                    send_post_save = True

                if kwargs:
                    if not completed:
                        # only update step changes on non completed objects.
                        # this results in non updated records for nonsense
                        query = query.filter(done_at__isnull=True)
                    with transaction.atomic():
                        query.update(**kwargs)

                    if send_post_save:
                        instance = query[0]
                        post_save.send(
                            BackgroundProcess,
                            instance=instance,
                            created=False
                        )

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
