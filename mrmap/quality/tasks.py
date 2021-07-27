"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from celery.utils.log import get_task_logger
from quality.enums import ConformityTypeEnum
from quality.models import ConformityCheckConfiguration, ConformityCheckRun, \
    ConformityCheckConfigurationExternal
from quality.plugins.etf import QualityEtf, ValidationDocumentProvider, \
    EtfClient
from quality.plugins.internal import QualityInternal
from resourceNew.models.metadata import DatasetMetadata
from structure.AbortedException import AbortedException

logger = get_task_logger(__name__)


@shared_task(name='run_quality_check', base=AbortableTask, bind=True)
def run_quality_check(self, run_id: int, s: str):
    run = ConformityCheckRun.objects.get(id=run_id)
    if run is None:
        raise Exception(f'No conformity check run with id {run_id}')
    config = run.conformity_check_configuration
    # TODO handle other resources
    metadata = run.metadata

    if config.conformity_type == ConformityTypeEnum.INTERNAL.value:
        checker = QualityInternal(run)
    elif config.conformity_type == ConformityTypeEnum.ETF.value:
        config_ext = ConformityCheckConfigurationExternal.objects.get(
            pk=config.pk)
        document_provider = ValidationDocumentProvider(metadata, config_ext)
        client = EtfClient(config_ext.external_url)
        checker = QualityEtf(run, config_ext, document_provider, client)
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


@shared_task(name="complete_validation_task", bind=True)
def complete_validation(self, run_id: int):
    """ Handles the completed validation process.

        Handler for completing the validation process. This method
        takes care of deleting the PeriodicTask and adding a
        new GroupActivity.

        Note: This method should be used to handle the completed validation
              process (passed, failed). Use complete_validation_error for
              handling any kind of unexpected exceptions during the validation.

        Args:
            run_id (int): The id of the ConformityCheckRun.
        Returns:
            nothing
    """
    try:
        run = ConformityCheckRun.objects.get(pk=run_id)
        # task is still running
        if run.passed is None:
            return

    except ConformityCheckRun.DoesNotExist as e:
        logger.error("Could not complete validation. ", e)


@shared_task(name="complete_validation_error_task")
def complete_validation_error(request, exc, traceback, run_id: int = None):
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
            run (int): The id of the conformity check run
        Returns:
            nothing
    """
    try:
        # delete run, if it was manually aborted
        if isinstance(exc, AbortedException):
            try:
                ConformityCheckRun.objects.filter(id=run_id).delete()
            except ConformityCheckRun.DoesNotExist:
                pass

    except ConformityCheckRun.DoesNotExist as e:
        logger.error("Could not complete error task. ", e)
