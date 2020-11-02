"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""

from quality.models import ConformityCheckRun, \
    ConformityCheckConfiguration
from quality.plugins.internal import QualityInternal
from service.models import Metadata


class Quality:

    @staticmethod
    def run_check(metadata: Metadata,
                  config: ConformityCheckConfiguration):
        if metadata is None:
            raise Exception("Metadata not defined.")
        if config is None:
            raise Exception("Config not defined.")

        checker = QualityInternal(metadata, config)
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
