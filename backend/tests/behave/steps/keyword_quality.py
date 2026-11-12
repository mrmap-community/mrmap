"""Domain steps of the keyword quality indicator (issue #919).

The scenarios harvest through the code the task calls - a stored metadata
file of a run imported by `md_metadata_file_to_db` - because the writer of
the flag lives in that finalization, not in an endpoint. The documents are
copies of the mapper corpus; behave runs without Celery, so the import runs
synchronously here exactly like the task would.
"""

import tempfile
from datetime import timedelta

from behave import given, then
from django.core.files.base import ContentFile
from django.db.models import F
from django.test import override_settings

from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.metadata import DatasetMetadataRecord
from tests.django.registry.mappers.tests_import_keyword_quality import \
    APPOSITION, GDI_BW_LIST, keyword_document


def _harvest(context, document):
    """Stores one document as the record of a run and imports it."""
    if not hasattr(context, "_quality_media"):
        media = tempfile.TemporaryDirectory()
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        context._quality_media = (media, override)
    job = HarvestingJob.objects.create(total_records=1, phase=Phase.RECORDS_TO_DB)
    file = TemporaryMdMetadataFile(job=job)
    file.md_metadata_file.save("record.xml", ContentFile(document), save=False)
    file.save()
    imported, _updated, _existed = file.md_metadata_file_to_db()[0]
    context.quality_record_id = str(imported.pk)


@given("the catalogue published a record whose keyword publishes several values")
def publish_merged_keyword(context):
    context.quality_document = keyword_document(
        "dataset.xml", "de.behave.keywordlist", [GDI_BW_LIST])
    _harvest(context, context.quality_document)


@given("the catalogue published a record whose keyword carries one comma in a short phrase")
def publish_legitimate_comma(context):
    context.quality_document = keyword_document(
        "dataset.xml", "de.behave.keywordlist", [APPOSITION])
    _harvest(context, context.quality_document)


@given("the catalogue corrects the record and republishes it")
def publish_correction(context):
    DatasetMetadataRecord.objects.filter(pk=context.quality_record_id).update(
        date_stamp=F("date_stamp") - timedelta(days=1))
    corrected = keyword_document(
        "dataset.xml", "de.behave.keywordlist", GDI_BW_LIST.split(","))
    _harvest(context, corrected)


def _record_body(context):
    # the registry router is registered without trailing slashes
    response = context.client.get(
        f"/api/registry/dataset-metadata/{context.quality_record_id}",
        HTTP_ACCEPT="application/vnd.api+json")
    assert response.status_code == 200, response.content[:400]
    return response.json()["data"]["attributes"]


@then("the harvested record answers its insufficient quality")
def answers_quality(context):
    text = _record_body(context)["insufficientQuality"]
    assert "publishes 11 values in one gmd:keyword element" in text, text
    assert "Flächennutzungsplan WN Remshalden" in text, text


@then("the harvested record answers no insufficient quality")
def answers_no_quality(context):
    assert _record_body(context)["insufficientQuality"] == ""


def _filtered_ids(context, value):
    response = context.client.get(
        f"/api/registry/dataset-metadata?filter[has_insufficient_quality]={value}",
        HTTP_ACCEPT="application/vnd.api+json")
    assert response.status_code == 200, response.content[:400]
    return [row["id"] for row in response.json()["data"]]


@then("the insufficient quality filter answers the harvested record")
def filter_answers_record(context):
    assert context.quality_record_id in _filtered_ids(context, "true")
    assert context.quality_record_id not in _filtered_ids(context, "false")


@then("the insufficient quality filter answers no record")
def filter_answers_nothing(context):
    assert _filtered_ids(context, "true") == []


def after_scenario(context, scenario):
    media_override = getattr(context, "_quality_media", None)
    if media_override is not None:
        media, override = media_override
        override.disable()
        media.cleanup()
        del context._quality_media
