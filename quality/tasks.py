from time import sleep

from celery import shared_task, states
from celery.contrib.abortable import AbortableTask
from celery.utils.log import get_task_logger
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from quality.enums import ConformityTypeEnum
from quality.models import ConformityCheckConfiguration, ConformityCheckRun
from quality.plugins.etf import QualityEtf
from quality.plugins.internal import QualityInternal
from service.models import Metadata
from structure.AbortedException import AbortedException
from structure.models import MrMapUser, MrMapGroup, PendingTask
from users.helper.user_helper import create_group_activity

logger = get_task_logger(__name__)


@shared_task(name='run_quality_check', base=AbortableTask)
def run_quality_check(config_id: int, metadata_id: int):
    config = ConformityCheckConfiguration.objects.get(pk=config_id)
    metadata = Metadata.objects.get(pk=metadata_id)
    if metadata is None:
        raise Exception("Metadata not defined.")
    if config is None:
        raise Exception(
            "Could not check conformity. ConformityCheckConfiguration is "
            "None.")

    if config.conformity_type == ConformityTypeEnum.INTERNAL.value:
        checker = QualityInternal(metadata, config)
    elif config.conformity_type == ConformityTypeEnum.ETF.value:
        checker = QualityEtf(metadata, config)
    else:
        raise Exception(
            f"Could not check conformity. Invalid conformity type: "
            f"{config.conformity_type}.")

    # check if this method was called as async task
    aborted_method = getattr(run_quality_check, 'is_aborted', None)
    if callable(aborted_method) and run_quality_check.is_aborted():
        raise AbortedException()

    run = checker.run()

    # check if this method was called as async task
    aborted_method = getattr(run_quality_check, 'is_aborted', None)
    if callable(aborted_method) and run_quality_check.is_aborted():
        raise AbortedException()

    return run.pk


@shared_task(name="complete_validation_task")
def complete_validation(run_id: int, user_id: int = None, group_id: int = None):
    """ Handles the completed validation process.

        Handler for completing the validation process. This method
        takes care of deleting the PeriodicTask and adding a
        new GroupActivity.

        Note: This method should be used to handle the completed validation
              process (passed, failed). Use complete_validation_error for
              handling any kind of unexpected exceptions during the validation.

        Args:
            run_id (int): The id of the ConformityCheckRun.
        Keyword arguments:
            user_id (int): The id of the user that triggered the run.
            group_id (int): the id of the group that the validated metadata
            object belongs to.
        Returns:
            nothing
    """
    parent_task_id = complete_validation.request.parent_id

    run = ConformityCheckRun.objects.get(pk=run_id)
    if parent_task_id is not None:
        try:
            pt = PendingTask.objects.get(task_id=parent_task_id)
            pt.progress = 100
            pt.save()
            sleep(2)
            pt.delete()
        except PendingTask.DoesNotExist:
            pass

    # task is still running
    if run.passed is None:
        return

    group = MrMapGroup.objects.get(pk=group_id)
    user = MrMapUser.objects.get(pk=user_id)

    title = _(f'Validation {"succeeded" if run.passed else "failed"}')
    href = reverse('resource:detail', args=(run.metadata.pk,))
    content = _(
        f'for <a href="{href}">'
        f'{run.metadata.title}</a> '
        f'with <i>{run.conformity_check_configuration}</i>.')
    create_group_activity(
        group=group,
        user=user,
        msg=title,
        metadata_title=content
    )


@shared_task(name="complete_validation_error_task")
def complete_validation_error(request, exc, traceback, user_id: int = None, group_id: int = None,
                              config_id: int = None, metadata_id: str = None):
    """ Handles the aborted validation process.

        Handler for completing the aborted validation process. This method
        takes care of deleting the PeriodicTask and adding a
        new GroupActivity.

        Note: This method should be used to handle the aborted validation
              process (e.g. unhandled Exceptions). Use complete_validation for
              handling the completed validation process.

        Args:
            *args: positional arguments
        Keyword arguments:
            user_id (int): The id of the user that triggered the run.
            group_id (int): the id of the group that the validated metadata
            object belongs to.
            config_id (int): The id of the ConformityCheckConfiguration.
            metadata_id (uuid): The id of the validated metadata object.
        Returns:
            nothing
    """
    parent_task_id = complete_validation_error.request.parent_id

    if parent_task_id is not None:
        try:
            pt = PendingTask.objects.get(task_id=parent_task_id)
            pt.delete()
        except PendingTask.DoesNotExist:
            pass

    config = ConformityCheckConfiguration.objects.get(pk=config_id)
    metadata = Metadata.objects.get(pk=metadata_id)
    group = MrMapGroup.objects.get(pk=group_id)
    user = MrMapUser.objects.get(pk=user_id)

    # delete run, if it was manually aborted
    if isinstance(exc, AbortedException):
        try:
            run = ConformityCheckRun.objects.get_latest_check(metadata)
            run.delete()
        except ConformityCheckRun.DoesNotExist:
            pass

    title = _(f'Validation aborted')
    content = _(
        f'for <a href="resource/detail/{metadata.id}">'
        f'{metadata.title}</a> '
        f'with <i>{config}</i>.')
    create_group_activity(
        group=group,
        user=user,
        msg=title,
        metadata_title=content
    )
