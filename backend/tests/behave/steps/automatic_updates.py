import json
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse
from guardian.shortcuts import assign_perm
from MrMap.settings import BASE_DIR
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import WebFeatureService, WebMapService
from registry.models.update import WebFeatureServiceUpdateJob, WebMapServiceUpdateJob
from requests.sessions import Session
from tests.django.utils import MockResponse


SERVICE_CASES = {
    "WMS": (WebMapService, WebMapServiceUpdateJob,
            "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3", "layers", "layer",
            "1.3.0", "node1.3.1", "node1.4"),
    "WFS": (WebFeatureService, WebFeatureServiceUpdateJob,
            "9cc4889d-0cd4-4c3b-8975-58de6d30db41", "featuretypes", "featuretype",
            "2.0.0", "node2", "node+"),
}


def rollback_automatic_update(atomic):
    # Fixtures are loaded once per feature. Roll back even a failed scenario,
    # including its pending on_commit callbacks, before the next one uses them.
    transaction.set_rollback(True)
    atomic.__exit__(None, None, None)


@given("the {service} capabilities contain {changes}")
def prepare_automatic_update(context, service, changes):
    atomic = transaction.atomic()
    atomic.__enter__()
    context.add_cleanup(rollback_automatic_update, atomic)

    (service_model, job_model, service_id, relation, element, version,
     removed_identifier, added_identifier) = SERVICE_CASES[service]
    context.automatic_service = service_model.objects.get(pk=service_id)
    context.automatic_relation = relation
    context.automatic_element = element
    context.removed_identifier = removed_identifier
    context.added_identifier = added_identifier
    context.original_element_ids = dict(
        getattr(context.automatic_service, relation).values_list("identifier", "pk"))
    capabilities = Path(BASE_DIR) / "tests/django/test_data/capabilities" / service.lower()
    original = (capabilities / f"fixture_{version}.xml").read_bytes()
    context.automatic_service.xml_backup_file = SimpleUploadedFile("capabilities.xml", original)
    context.automatic_service.save()

    if changes == "additions only":
        remote = (capabilities / f"one_new_{element}_update_fixture_{version}.xml").read_bytes()
    elif changes == "removals only":
        remote = (capabilities / f"one_removed_{element}_update_fixture_{version}.xml").read_bytes()
    elif changes == "an identifier rename":
        context.renamed_identifier = f"{removed_identifier}-renamed"
        old_name = f"<Name>{removed_identifier}</Name>"
        new_name = f"<Name>{context.renamed_identifier}</Name>"
        assert old_name.encode() in original
        remote = original.replace(old_name.encode(), new_name.encode(), 1)
    else:
        raise AssertionError(f"Unknown capabilities change: {changes}")

    http = patch.object(Session, "send", return_value=MockResponse(remote.decode("UTF-8")))
    context.automatic_remote = http.start()
    context.patchers.append(http)
    enqueue = patch(f"registry.models.update.run_{service.lower()}_update.apply_async")
    enqueue.start()
    context.patchers.append(enqueue)
    job_model.objects.filter(service=context.automatic_service).delete()
    context.automatic_job = job_model.objects.create(service=context.automatic_service)


@when("the automatic service update runs")
@when("the automatic service update resumes")
def run_automatic_update(context):
    # Fetch a fresh job, as a worker would, rather than reusing cached candidates.
    context.automatic_job = type(context.automatic_job).objects.get(pk=context.automatic_job.pk)
    context.automatic_job.update()


@when("I use the automatic service update job endpoint")
def use_automatic_update_endpoint(context):
    view_name = f"registry:{context.automatic_job._meta.model_name}-detail"
    context.endpoint = reverse(view_name, args=[context.automatic_job.pk])


def assert_completed_update(context):
    context.automatic_job.refresh_from_db()
    assert context.automatic_job.status == UpdateJobStatusEnum.UPDATED.value
    assert context.automatic_job.done_at is not None
    assert not context.automatic_job.mappings.exists()
    assert not type(context.automatic_service).objects.filter(
        update_candidate_of=context.automatic_service).exists()
    context.automatic_remote.assert_called_once()


def published_element_ids(context):
    return dict(getattr(context.automatic_service, context.automatic_relation).values_list("identifier", "pk"))


@then("the added service element is published with existing element IDs preserved")
def check_published_addition(context):
    assert_completed_update(context)
    published = published_element_ids(context)
    assert set(published) == set(context.original_element_ids) | {context.added_identifier}
    for identifier, pk in context.original_element_ids.items():
        assert published[identifier] == pk


@then("the removed service element is deleted with remaining element IDs preserved")
def check_published_removal(context):
    assert_completed_update(context)
    expected = context.original_element_ids.copy()
    expected.pop(context.removed_identifier)
    assert published_element_ids(context) == expected


@then("the service update awaits review without replacing existing elements")
def check_pending_review(context):
    context.automatic_job.refresh_from_db()
    assert context.automatic_job.status == UpdateJobStatusEnum.REVIEW_REQUIRED.value
    assert context.automatic_job.done_at is None
    assert type(context.automatic_service).objects.filter(
        update_candidate_of=context.automatic_service).exists()
    assert context.automatic_job.mappings.filter(is_confirmed=False).count() == 1
    assert published_element_ids(context) == context.original_element_ids


@given("I review the service element rename")
def prepare_rename_review(context):
    mapping = context.automatic_job.mappings.get(is_confirmed=False)
    user = get_user_model().objects.get(username="User1")
    assign_perm(f"registry.change_{mapping._meta.model_name}", user)
    assign_perm(f"registry.change_{mapping._meta.model_name}", user, mapping)
    element_model = mapping._meta.get_field(f"old_{context.automatic_element}").related_model
    context.endpoint = reverse(f"registry:{mapping._meta.model_name}-detail", args=[mapping.pk])
    old_relationship = "oldLayer" if context.automatic_element == "layer" else "oldFeaturetype"
    context.payload = json.dumps({
        "data": {
            "type": mapping._meta.object_name,
            "id": str(mapping.pk),
            "attributes": {"isConfirmed": True},
            "relationships": {
                old_relationship: {
                    "data": {
                        "type": element_model._meta.object_name,
                        "id": str(context.original_element_ids[context.removed_identifier]),
                    }
                }
            },
        }
    })


@then("the renamed service element retains its existing ID")
def check_reviewed_rename(context):
    assert_completed_update(context)
    expected = context.original_element_ids.copy()
    expected[context.renamed_identifier] = expected.pop(context.removed_identifier)
    assert published_element_ids(context) == expected
