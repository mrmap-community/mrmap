from time import sleep

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils.translation import gettext_lazy as _

from quality.settings import quality_logger
from service.helper.enums import PendingTaskEnum
from structure.models import PendingTask, MrMapUser, MrMapGroup
from users.helper.user_helper import create_group_activity

logger = get_task_logger(__name__)


@shared_task(name="my_task")
def my_task(user_id, group_id):
    curr_task_id = my_task.request.id

    try:
        user = MrMapUser.objects.get(pk=user_id)
        group = MrMapGroup.objects.get(pk=group_id)
    except (MrMapUser.DoesNotExist, MrMapGroup.DoesNotExist):
        logger.error(
            f'User with id {user_id} or group with id {group_id} does not '
            f'exist.')
        create_group_activity(
            group=group,
            user=user,
            msg=_(f'Validation Failed'),
            metadata_title=_('Could not start the validation for metadataXY.')
        )
        return

    pending_task_db = None
    if curr_task_id is not None:
        # create db object, so we know which pending task is still ongoing
        pending_task_db = PendingTask()
        # pending_task_db.created_by = MrMapGroup.objects.get(
        #     id=form.cleaned_data['registering_with_group'].id)
        pending_task_db.created_by = group
        pending_task_db.task_id = curr_task_id
        pending_task_db.description = '{"service": "Hello world"}'
        # pending_task_db.description = json.dumps({
        #     "service": form.cleaned_data['uri'],
        #     "phase": "Parsing",
        # })
        pending_task_db.type = PendingTaskEnum.VALIDATE.value
        pending_task_db.save()

    sleep(5)

    create_group_activity(
        group=group,
        user=user,
        msg=_(f"<i>Validation Complete YES!</i>"),
        metadata_title=_("metadata title")
    )
    if pending_task_db is not None:
        pending_task_db.delete()
