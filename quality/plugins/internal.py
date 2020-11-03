from quality.models import ConformityCheckConfigurationInternal, ConformityCheckRun, ConformityCheckConfiguration
from service.models import Metadata


class InternalQuality:

    def __init__(self, metadata: Metadata,
                 base_config: ConformityCheckConfiguration):
        self.metadata = metadata
        self.config = ConformityCheckConfigurationInternal.objects.get(
            pk=base_config.pk)

    def run(self):
        run = ConformityCheckRun.objects.create(
            metadata=self.metadata, conformity_check_configuration=self.config)
        pass
