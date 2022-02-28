from celery import Task
from celery.signals import task_prerun
from django.contrib.contenttypes.models import ContentType
from django_celery_results.models import TaskResult

from notify.models import BackgroundProcess


@task_prerun.connect
def get_background_process(task, *args, **kwargs):
    print(kwargs["kwargs"])
    background_process_pk = kwargs["kwargs"].get("background_process_pk", None)
    print(background_process_pk)
    if background_process_pk:
        try:
            task.background_process = BackgroundProcess.objects.get(
                pk=background_process_pk)
            print(task.background_process)
        except:
            pass


class BackgroundProcessBased(Task):
    thread_appended = False

    def update_background_process(self, phase: str = "", service=None):
        print(self.request)
        print(self.background_process)
        if self.request and self.request.id and hasattr(self, "background_process"):

            if not self.thread_appended:
                self.background_process.threads.add(
                    *TaskResult.objects.filter(task_id=self.request.id))
                self.thread_appended = True
            if phase:
                self.background_process.phase = phase
                self.background_process.save()
            if service:
                try:
                    service_ct = ContentType.objects.get_for_model(service)
                    self.background_process.related_resource_type = service_ct.pk
                    self.background_process.related_id = service.pk
                    self.background_process.save()
                except:
                    pass
