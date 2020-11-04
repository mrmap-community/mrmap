from celery import shared_task
from django.utils.translation import gettext_lazy as _

from quality.enums import ConformityTypeEnum
from quality.models import ConformityCheckConfiguration
from quality.plugins.etf import QualityEtf
from quality.plugins.internal import QualityInternal
from service.helper.enums import PendingTaskEnum
from service.models import Metadata
from structure.models import MrMapUser, MrMapGroup, PendingTask
from users.helper.user_helper import create_group_activity


@shared_task(name='run_quality_check')
def run_quality_check(config_id: int, metadata_id: int, user_id, group_id):
    curr_task_id = run_quality_check.request.id

    try:
        user = MrMapUser.objects.get(pk=user_id)
        group = MrMapGroup.objects.get(pk=group_id)
    except (MrMapUser.DoesNotExist, MrMapGroup.DoesNotExist):
        create_group_activity(
            group=group,
            user=user,
            msg=_(f'Validation Failed'),
            metadata_title=_('Could not start the validation for metadataXY.')
        )
        raise Exception("User or group does not exist.")

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

    config = ConformityCheckConfiguration.objects.get(pk=config_id)
    metadata = Metadata.objects.get(pk=metadata_id)
    if metadata is None:
        raise Exception("Metadata not defined.")
    if config is None:
        raise Exception(
            "Could not check conformity. ConformityCheckConfiguration is "
            "None.")
    checker = None
    if config.conformity_type == ConformityTypeEnum.INTERNAL.value:
        checker = QualityInternal(metadata, config)
    elif config.conformity_type == ConformityTypeEnum.ETF.value:
        checker = QualityEtf(metadata, config)
    else:
        raise Exception(
            f"Could not check conformity. Invalid conformity type: "
            f"{config.conformity_type}.")
    checker.run()

    create_group_activity(
        group=group,
        user=user,
        msg=_(f"<i>Validation Complete YES!</i>"),
        metadata_title=_("metadata title")
    )
    if pending_task_db is not None:
        pending_task_db.delete()
