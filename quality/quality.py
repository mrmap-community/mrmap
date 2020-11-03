"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""

from quality.enums import ConformityTypeEnum
from quality.models import ConformityCheckRun, ConformityCheckConfiguration
from quality.plugins.etf import EtfQuality
from quality.plugins.internal import InternalQuality
from service.models import Metadata


class Quality:

    @staticmethod
    def run_check(metadata: Metadata,
                  config: ConformityCheckConfiguration):
        if metadata is None:
            raise Exception("Metadata not defined.")
        if config is None:
            raise Exception(
                "Could not check conformity. ConformityCheckConfiguration is "
                "None.")

        checker = None
        if config.conformity_type == ConformityTypeEnum.INTERNAL.value:
            checker = InternalQuality(metadata, config)
        elif config.conformity_type == ConformityTypeEnum.ETF.value:
            checker = EtfQuality(metadata, config)
        else:
            raise Exception(
                f"Could not check conformity. Invalid conformity type: "
                f"{config.conformity_type}.")
        checker.run()

    @staticmethod
    def has_running_check(metadata: Metadata) -> bool:
        """ Checks if the given metadata object has a non-finished
        ConformityCheckRun.

            Returns:
                True, if a non-finished ConformityCheckRun was found,
                false otherwise.
        """
        running_checks = ConformityCheckRun.objects.filter(
            metadata=metadata, passed__isnull=True).count()
        return running_checks != 0
