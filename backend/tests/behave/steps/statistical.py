from datetime import datetime, timezone

from behave import given
from django.db import transaction
from registry.models.service import FeatureType


WFS1_ID = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
WFS2_ID = "72bda0a1-a808-48ba-ab1d-bf03081263df"
FEATURETYPE1_ID = "efba476a-d3ff-44f8-a0db-7f2c811f7247"
FEATURETYPE2_ID = "fa8713a6-875f-48b4-95f2-f9bb7cf47001"
OTHER_FEATURETYPE_ID = "9dfcdbf6-b735-41a3-b7f7-353a6344b134"


def rollback_featuretype_history(atomic):
    transaction.set_rollback(True)
    atomic.__exit__(None, None, None)


@given("the WFS history contains service-specific feature type changes")
def prepare_featuretype_statistics(context):
    # Fixtures are shared between scenarios, so restore their history even
    # when an assertion fails, as automatic_updates.py does for its setup.
    atomic = transaction.atomic()
    atomic.__enter__()
    context.add_cleanup(rollback_featuretype_history, atomic)

    history = FeatureType.change_log.model.objects
    history.filter(service_id__in=[WFS1_ID, WFS2_ID]).delete()
    first_day = datetime(2022, 2, 1, 12, tzinfo=timezone.utc)
    last_day = datetime(2022, 3, 1, 12, tzinfo=timezone.utc)
    for service_id, featuretype_id, day, change, title in [
        (WFS1_ID, FEATURETYPE1_ID, first_day, "+", "Original title"),
        (WFS1_ID, FEATURETYPE2_ID, first_day, "+", "Removed feature type"),
        (WFS2_ID, OTHER_FEATURETYPE_ID, first_day, "+", "Other service"),
        (WFS1_ID, FEATURETYPE1_ID, last_day, "~", "Updated title"),
        (WFS1_ID, FEATURETYPE2_ID, last_day, "-", "Removed feature type"),
    ]:
        history.create(
            id=featuretype_id, history_relation_id=featuretype_id,
            service_id=service_id, default_reference_system_id=1,
            title=title, history_date=day, history_type=change,
        )
