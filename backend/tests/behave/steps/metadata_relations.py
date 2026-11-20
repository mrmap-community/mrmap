"""Domain steps of the metadata relation write scenarios (#985).

The pattern is the one ``steps/object_permissions.py`` sets: ``Given`` steps
create the rows and grants the scenarios assert upon, ``Then`` steps read the
database. The pair the scenarios couple is the mixed #829 service record and
the first RBSN dataset record of the shared fixture set - the records ARE
loaded from fixtures; only the CURATOR declaration between them is what a
scenario declares or asserts through the api.
"""
from behave import given, then, when
from django.contrib.auth import get_user_model
from guardian.shortcuts import assign_perm
from registry.enums.metadata import MetadataOriginEnum
from registry.models.metadata import (DatasetMetadataRecord, MetadataRelation,
                                      ServiceMetadataRecord)

#: the service metadata record of ``test_csw_mixed_records.json``
SERVICE_RECORD_ID = "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"

#: the first dataset record of ``test_datasetmetadata.json``
DATASET_RECORD_ID = "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"


def _pair_relation():
    return MetadataRelation.objects.filter(
        service_metadata_id=SERVICE_RECORD_ID,
        dataset_metadata_id=DATASET_RECORD_ID,
        is_internal=True,
        origin=MetadataOriginEnum.EDITOR.value).first()


@given('a curator "{username}" granted to couple the records exists')
def create_granted_curator(context, username):
    """A user with D11's exact answer: change over one record end, view
    over every end - and no role which holds anything over the join row.
    """
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(username=username)
    user.set_password(username)
    # not a member of Default-Permissions - the scenario hands out exactly
    # the grants the coupling needs, explicitly
    user.groups.clear()
    user.save()
    service = ServiceMetadataRecord.objects.get(pk=SERVICE_RECORD_ID)
    dataset = DatasetMetadataRecord.objects.get(pk=DATASET_RECORD_ID)
    assign_perm("registry.change_servicemetadatarecord", user, service)
    assign_perm("registry.view_servicemetadatarecord", user, service)
    assign_perm("registry.view_datasetmetadatarecord", user, dataset)


@given('the editor has declared the pair of the records')
def declare_editor_pair(context):
    """The curator's declaration, asserted through the model method the api
    itself runs - the state the DELETE scenarios start from.
    """
    service = ServiceMetadataRecord.objects.get(pk=SERVICE_RECORD_ID)
    dataset = DatasetMetadataRecord.objects.get(pk=DATASET_RECORD_ID)
    service.add_record_relation(
        dataset, origin=MetadataOriginEnum.EDITOR.value, is_internal=True)


@then('the pair relation is answered exactly once')
def pair_answered_once(context):
    """One row for one pair - re-POSTing the same pair asserts the standing
    row instead of stacking a second one (#985).
    """
    count = MetadataRelation.objects.filter(
        service_metadata_id=SERVICE_RECORD_ID,
        dataset_metadata_id=DATASET_RECORD_ID).count()
    context.test.assertEqual(
        count, 1, f"the pair answers {count} relation rows, not one")


@then('the harvested relation of the fixture is still standing')
def harvested_relation_standing(context):
    """The CAPABILITIES kind relation of ``test_datasetmetadata.json``
    survives the refused DELETE untouched.
    """
    context.test.assertTrue(
        MetadataRelation.objects.filter(pk=1).exists(),
        "a harvested coupling was taken back through the relation endpoint")


@when('I delete the declared pair relation')
def delete_declared_pair(context):
    """The DELETE request of the row the Given step (or a POST of the same
    scenario) declared: the endpoint is asked at the row's own url.
    """
    relation = _pair_relation()
    if relation is None:
        raise Exception("no editor pair relation was declared to delete")
    context.endpoint = (
        "http://localhost:8000/api/registry/metadata-relations/"
        f"{relation.pk}")
    context.execute_steps("When I send the request with DELETE method")


@then('the declared pair relation is gone')
def pair_relation_gone(context):
    context.test.assertIsNone(
        _pair_relation(),
        "the editor's pair relation is still standing after its take back")
