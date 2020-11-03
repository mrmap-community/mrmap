from celery import shared_task

from quality.enums import ConformityTypeEnum
from quality.models import ConformityCheckConfiguration
from quality.plugins.etf import QualityEtf
from quality.plugins.internal import QualityInternal
from service.models import Metadata


@shared_task(name='run_quality_check')
def run_quality_check(config_id: int, metadata_id: int):
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
