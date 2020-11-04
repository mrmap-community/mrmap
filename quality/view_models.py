from quality.models import ConformityCheckConfiguration, ConformityCheckRun
from service.models import Metadata


def get_quality_dropdown_model(metadata: Metadata, no_text=False):
    is_running = False
    valid = None
    try:
        last_check = ConformityCheckRun.objects.get_latest_check(metadata)
        is_running = last_check.is_running()
        valid = last_check.passed
    except ConformityCheckRun.DoesNotExist:
        pass

    configs = ConformityCheckConfiguration.objects.get_for_metadata_type(
        metadata.metadata_type)
    disabled = is_running or len(configs) == 0

    return {
        "running": is_running,
        "valid": valid,
        "configs": configs,
        "disabled": disabled,
        "metadata_id": metadata.id,
        "no_text": no_text,
    }
