"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""

from quality.enums import ConformityTypeEnum
from quality.models import ConformityCheckConfiguration
from quality.plugins.etf import QualityEtf
from quality.plugins.internal import QualityInternal
from service.models import Metadata


def run_check(metadata: Metadata,
              config: ConformityCheckConfiguration):
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
    checker.run()
