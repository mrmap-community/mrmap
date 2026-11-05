from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from MrMap.settings import BASE_DIR
from registry.models.harvest import HarvestingJob
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, MetadataContact)
from rest_framework.test import APIClient

#: Prefix of the feature tag that requests one fixture file, e.g. ``@fixtures:test_wms.json``.
FIXTURE_TAG_PREFIX = "fixtures:"

#: Tag of a feature that needs no data at all beyond the users ``before_all`` loads.
NO_FIXTURES_TAG = "no_fixtures"

# rows which only the application record features of #830 declare; the pks belong
# to test_applicationmetadata.json and test_applicationharvesting.json
APPLICATION_CONTACT_PKS = [1235, 1236]
APPLICATION_RECORD_PKS = [
    "a11c0000-0000-4000-8000-000000000001",
    "a11c0000-0000-4000-8000-000000000002",
]
APPLICATION_HARVESTING_JOB_PKS = [903]


def before_all(context):
    # see https://github.com/behave/behave-django/issues/114... fixure behaviour is broken with --simple
    # basicly there are users and groups

    fixtures = ['test_users.json']
    call_command("loaddata", *fixtures, verbosity=0)


def requested_fixtures(feature):
    """Fixture files that the ``@fixtures:<file>.json`` tags of a feature request."""
    return [tag[len(FIXTURE_TAG_PREFIX):]
            for tag in getattr(feature, "tags", [])
            if tag.startswith(FIXTURE_TAG_PREFIX)]


def load_fixtures(fixtures):
    call_command("loaddata", *fixtures, verbosity=0)

    if 'test_datasetmetadata.json' in fixtures:
        # fix dataset xml files
        rbsn_rr_file = open(
            f"{BASE_DIR}/tests/django/test_data/RBSN_RR.xml", mode="rb")
        rbsn_rr_bytes = rbsn_rr_file.read()
        rbsn_rr = DatasetMetadataRecord.objects.get(
            pk="d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4")
        rbsn_rr.xml_backup_file = SimpleUploadedFile(
            'md_metadata.xml', rbsn_rr_bytes)
        rbsn_rr.save()
        rbsn_rr_file.close()

        rbsn_rh_file = open(
            f"{BASE_DIR}/tests/django/test_data/RBSN_RH.xml", mode="rb")
        rbsn_rh_bytes = rbsn_rh_file.read()
        rbsn_rh = DatasetMetadataRecord.objects.get(
            pk="9e57ada9-d3bf-403f-bd6c-eb4d38f0ef8e")
        rbsn_rh.xml_backup_file = SimpleUploadedFile(
            'md_metadata.xml', rbsn_rh_bytes)
        rbsn_rh.save()
        rbsn_rh_file.close()


def before_feature(context, feature):
    """Load the data a feature declared with its tags.

    The order of the ``@fixtures:`` tags is the order ``loaddata`` reads them in, which is what
    resolves foreign keys between fixture files; keep it if you edit the tags.
    """
    requested = requested_fixtures(feature)
    if NO_FIXTURES_TAG in getattr(feature, "tags", []):
        if requested:
            raise AssertionError(
                f"{feature.filename}: @no_fixtures contradicts the requested {requested}")
        return
    if not requested:
        raise AssertionError(
            f"{feature.filename}: declare one @fixtures:<file>.json tag per fixture, or "
            f"@{NO_FIXTURES_TAG} if the scenarios really need no rows. Loading nothing used to "
            f"happen silently whenever a title did not match the legacy mapping, and a feature "
            f"without data passes on 'meta.pagination.count == 0' without testing anything.")
    load_fixtures(requested)


def after_feature(context, feature):
    """Remove the rows of the application record fixtures of #830.

    The fixtures of a feature are loaded once per feature and not restored, so
    every row a feature declares stays visible to the features which run after
    it. The application rows are shared by three of the new features (they all
    load the same files) and the harvesting rows of them carry statistics whose
    counts the already green scenarios of the harvesting never saw; the feature
    which loaded them hands its rows back here. ``loaddata`` is idempotent over
    the primary keys, so the next of the three features simply loads them again.
    """
    requested = requested_fixtures(feature)
    if "test_applicationharvesting.json" in requested:
        # deleting the job cascades the harvested relations which hang from it
        HarvestingJob.objects.filter(pk__in=APPLICATION_HARVESTING_JOB_PKS).delete()
    if "test_applicationmetadata.json" in requested:
        # the record cascades its own harvested relations; the contact is what
        # RESTRICTs a deletion, so it goes last
        ApplicationMetadataRecord.objects.filter(pk__in=APPLICATION_RECORD_PKS).delete()
        MetadataContact.objects.filter(pk__in=APPLICATION_CONTACT_PKS).delete()


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77

    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()
    context.query_params = {}
    context.patchers = []


def after_scenario(context, scenario):
    for patcher in context.patchers:
        patcher.stop()


def after_step(context, step):
    """Dump what a failing or erroring step got back, so that the scenario explains itself."""
    if step.status not in (Status.failed, Status.error):
        return

    response = getattr(context, 'response', None)
    if not response:
        return

    print(f"failing step: {step.name}  # {step.filename}:{step.line}")
    content_type = response.get('Content-Type', '')
    print(f"response: {response.status_code} {content_type}")
    if 'text/html' in content_type:
        # the browsable API renderer answered, its page is noise here
        print("hint: the response is HTML and not JSON; the scenario needs the request header"
              " HTTP_ACCEPT with the value application/vnd.api+json")
        return
    print(response.content)
